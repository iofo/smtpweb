import mimetypes
import secrets
import time
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.requests import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from smtpweb.common.storage import EmailStorage
from smtpweb.web.mailbox_auth import MailboxAuth

STATIC_DIR = Path(__file__).parent / "static"
SESSION_COOKIE = "smtpweb_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30

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


class LoginPayload(BaseModel):
    username: str
    password: str


def create_app(
    storage: EmailStorage, mailbox_auth: MailboxAuth, cookie_secure: bool = False
) -> FastAPI:
    # docs_url/redoc_url/openapi_url disabled: this app has no open/anonymous
    # mode anywhere else, and the auto-generated API docs would otherwise be
    # the one unauthenticated thing exposing the full route/schema surface.
    app = FastAPI(title="smtpweb", docs_url=None, redoc_url=None, openapi_url=None)
    # token -> (mailbox, expires_at). Expired entries are evicted lazily
    # (on lookup) and swept opportunistically (on login), since nothing
    # else ever removes a session that its owner never logs out of.
    sessions: dict[str, tuple[str, float]] = {}

    def _sweep_expired_sessions() -> None:
        now = time.time()
        expired = [token for token, (_, expires_at) in sessions.items() if expires_at <= now]
        for token in expired:
            del sessions[token]

    def require_session(
        session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> str:
        entry = sessions.get(session) if session else None
        if entry is None:
            raise HTTPException(401, "Not authenticated")
        mailbox, expires_at = entry
        if expires_at <= time.time():
            sessions.pop(session, None)
            raise HTTPException(401, "Not authenticated")
        return mailbox

    @app.post("/api/login")
    def login(payload: LoginPayload, response: Response):
        mailbox = mailbox_auth.login(payload.username, payload.password)
        if mailbox is None:
            raise HTTPException(401, "Invalid credentials")
        _sweep_expired_sessions()
        token = secrets.token_urlsafe(32)
        sessions[token] = (mailbox, time.time() + SESSION_MAX_AGE_SECONDS)
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
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            sessions.pop(token, None)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(mailbox: str = Depends(require_session)):
        return {"username": mailbox}

    @app.get("/api/emails")
    def list_emails(mailbox: str = Depends(require_session)):
        return storage.list_emails(mailbox)

    @app.get("/api/emails/{email_id}")
    def get_email(email_id: str, mailbox: str = Depends(require_session)):
        try:
            meta = storage.get_email(mailbox, email_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Email not found") from None
        meta = dict(meta)
        meta["text_body"] = storage.get_body_text(mailbox, email_id)
        meta["html_body"] = storage.get_body_html(mailbox, email_id)
        return meta

    @app.get("/api/emails/{email_id}/raw")
    def get_raw(email_id: str, mailbox: str = Depends(require_session)):
        try:
            path = storage.get_raw_path(mailbox, email_id)
        except ValueError:
            raise HTTPException(400, "Invalid email id") from None
        if not path.exists():
            raise HTTPException(404, "Email not found")
        return FileResponse(path, media_type="message/rfc822", filename=f"{email_id}.eml")

    @app.get("/api/emails/{email_id}/attachments/{filename}")
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

    @app.delete("/api/emails/{email_id}", status_code=204)
    def delete_email(email_id: str, mailbox: str = Depends(require_session)):
        try:
            storage.delete_email(mailbox, email_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Email not found") from None

    @app.get("/api/emails/{email_id}/attachments/{filename}/thumbnail")
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

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
