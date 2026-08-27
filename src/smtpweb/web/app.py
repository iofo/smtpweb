import secrets
import time
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.requests import Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from smtpweb.mailbox_auth import MailboxAuth
from smtpweb.storage import EmailStorage

STATIC_DIR = Path(__file__).parent / "static"
SESSION_COOKIE = "smtpweb_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30


class LoginPayload(BaseModel):
    username: str
    password: str


def create_app(storage: EmailStorage, mailbox_auth: MailboxAuth) -> FastAPI:
    app = FastAPI(title="smtpweb")
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
            SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE_SECONDS
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
            raise HTTPException(404, "Email not found")
        meta = dict(meta)
        meta["text_body"] = storage.get_body_text(mailbox, email_id)
        meta["html_body"] = storage.get_body_html(mailbox, email_id)
        return meta

    @app.get("/api/emails/{email_id}/raw")
    def get_raw(email_id: str, mailbox: str = Depends(require_session)):
        try:
            path = storage.get_raw_path(mailbox, email_id)
        except ValueError:
            raise HTTPException(400, "Invalid email id")
        if not path.exists():
            raise HTTPException(404, "Email not found")
        return FileResponse(path, media_type="message/rfc822", filename=f"{email_id}.eml")

    @app.get("/api/emails/{email_id}/attachments/{filename}")
    def get_attachment(email_id: str, filename: str, mailbox: str = Depends(require_session)):
        try:
            path = storage.get_attachment_path(mailbox, email_id, filename)
        except ValueError:
            raise HTTPException(400, "Invalid attachment reference")
        if not path.exists():
            raise HTTPException(404, "Attachment not found")
        return FileResponse(path, filename=path.name)

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
