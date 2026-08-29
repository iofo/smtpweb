import mimetypes
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.requests import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from smtpweb.common.mailbox import sanitize_mailbox_name
from smtpweb.common.storage import EmailStorage
from smtpweb.web.login_rate_limit import LoginRateLimiter
from smtpweb.web.mailbox_auth import MailboxAuth
from smtpweb.web.session_store import SessionStore

STATIC_DIR = Path(__file__).parent / "static"
SESSION_COOKIE = "smtpweb_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60

# Types safe to render inline in the browser instead of forcing a download.
# Deliberately excludes text/html, image/svg+xml, and anything else that
# could carry an active script — since attachments are served from this
# app's own origin, rendering one of those inline would let a malicious
# "attachment" run script with access to the logged-in session (a stored
# XSS path). Determined from the filename extension (mimetypes), not the
# content-type the sending email claimed, so a mislabeled attachment can't
# talk its way into the inline allowlist.
INLINE_SAFE_MEDIA_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
}

# Applied to every file response — same rationale as INLINE_SAFE_MEDIA_TYPES:
# never let a browser's content-sniffing override our declared media type.
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff"}


class CachedStaticFiles(StaticFiles):
    """StaticFiles that forces a conditional request on every load.

    StaticFiles sets Last-Modified/ETag but no Cache-Control -- browsers
    then fall back to heuristic caching and can keep serving a stale
    cached copy after a new image is deployed without ever asking the
    server. `no-cache` (NOT `no-store`) forces a conditional request on
    every load; the ETag makes that cheap -- a 304 with no body when
    nothing changed, a fresh 200 when it has.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response


class LoginPayload(BaseModel):
    username: str
    password: str


def create_app(
    storage: EmailStorage,
    mailbox_auth: MailboxAuth,
    cookie_secure: bool = False,
    git_sha: str = "dev",
    login_max_attempts: int = LOGIN_MAX_ATTEMPTS,
    login_window_seconds: float = LOGIN_WINDOW_SECONDS,
) -> FastAPI:
    # docs_url/redoc_url/openapi_url disabled: this app has no open/anonymous
    # mode anywhere else, and the auto-generated API docs would otherwise be
    # the one unauthenticated thing exposing the full route/schema surface.
    app = FastAPI(title="smtpweb", docs_url=None, redoc_url=None, openapi_url=None)
    session_store = SessionStore(SESSION_MAX_AGE_SECONDS)
    login_rate_limiter = LoginRateLimiter(login_max_attempts, login_window_seconds)

    def require_session(
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> str:
        mailbox = session_store.get(session)
        if mailbox is None:
            raise HTTPException(401, "Not authenticated")
        return mailbox

    # Every route added to this router requires a valid session by
    # construction — the check runs before the route function at all, so a
    # route can't accidentally ship without it the way a per-route
    # `Depends(require_session)` could be forgotten on. Handlers that need
    # the mailbox value still declare `Depends(require_session)` themselves
    # too; FastAPI caches the dependency per request, so that's a second
    # read of the same result, not a second auth check.
    protected = APIRouter(dependencies=[Depends(require_session)])

    @app.get("/api/version")
    def version():
        return {"git_sha": git_sha}

    @app.post("/api/login")
    def login(payload: LoginPayload, response: Response):
        # Rate-limit by the normalized mailbox, not by client IP: it's the
        # per-mailbox password that's being guessed, and IP-based limits
        # are trivially defeated by a botnet anyway. Note the first-ever
        # login for a given mailbox always succeeds (self-service claim —
        # see MailboxAuth's docstring), so this only ever throttles wrong
        # passwords against an already-claimed mailbox.
        try:
            rate_limit_key = sanitize_mailbox_name(payload.username)
        except ValueError:
            rate_limit_key = None

        if rate_limit_key is not None and login_rate_limiter.is_limited(rate_limit_key):
            raise HTTPException(429, "Too many login attempts. Try again later.")

        mailbox = mailbox_auth.login(payload.username, payload.password)
        if mailbox is None:
            if rate_limit_key is not None:
                login_rate_limiter.record_failure(rate_limit_key)
            raise HTTPException(401, "Invalid credentials")

        login_rate_limiter.reset(mailbox)
        token = session_store.create(mailbox)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="lax",
            secure=cookie_secure,
            max_age=SESSION_MAX_AGE_SECONDS,
        )
        return {"username": mailbox}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        session_store.delete(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @protected.get("/api/me")
    def me(mailbox: str = Depends(require_session)):
        return {"username": mailbox}

    @protected.get("/api/emails")
    def list_emails(mailbox: str = Depends(require_session)):
        return storage.list_emails(mailbox)

    @protected.get("/api/emails/{email_id}")
    def get_email(email_id: str, mailbox: str = Depends(require_session)):
        try:
            meta = storage.get_email(mailbox, email_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Email not found") from None
        meta = dict(meta)
        meta["text_body"] = storage.get_body_text(mailbox, email_id)
        meta["html_body"] = storage.get_body_html(mailbox, email_id)
        return meta

    @protected.get("/api/emails/{email_id}/raw")
    def get_raw(email_id: str, mailbox: str = Depends(require_session)):
        try:
            path = storage.get_raw_path(mailbox, email_id)
        except ValueError:
            raise HTTPException(400, "Invalid email id") from None
        if not path.exists():
            raise HTTPException(404, "Email not found")
        return FileResponse(path, media_type="message/rfc822", filename=f"{email_id}.eml")

    @protected.get("/api/emails/{email_id}/attachments/{filename}")
    def get_attachment(email_id: str, filename: str, mailbox: str = Depends(require_session)):
        try:
            path = storage.get_attachment_path(mailbox, email_id, filename)
        except ValueError:
            raise HTTPException(400, "Invalid attachment reference") from None
        if not path.exists():
            raise HTTPException(404, "Attachment not found")

        media_type, _ = mimetypes.guess_type(path.name)
        media_type = media_type or "application/octet-stream"
        disposition = "inline" if media_type in INLINE_SAFE_MEDIA_TYPES else "attachment"

        return FileResponse(
            path,
            media_type=media_type,
            filename=path.name,
            content_disposition_type=disposition,
            headers=SECURITY_HEADERS,
        )

    @protected.delete("/api/emails/{email_id}", status_code=204)
    def delete_email(email_id: str, mailbox: str = Depends(require_session)):
        try:
            storage.delete_email(mailbox, email_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Email not found") from None

    @protected.get("/api/emails/{email_id}/attachments/{filename}/thumbnail")
    def get_attachment_thumbnail(
        email_id: str, filename: str, mailbox: str = Depends(require_session)
    ):
        try:
            path = storage.get_attachment_thumbnail_path(mailbox, email_id, filename)
        except ValueError:
            raise HTTPException(400, "Invalid attachment reference") from None
        if not path.exists():
            raise HTTPException(404, "Thumbnail not found")
        return FileResponse(
            path,
            media_type="image/png",
            filename=path.name,
            content_disposition_type="inline",
            headers=SECURITY_HEADERS,
        )

    app.include_router(protected)
    app.mount("/", CachedStaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
