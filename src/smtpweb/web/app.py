import base64
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.requests import Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from smtpweb.storage import EmailStorage

STATIC_DIR = Path(__file__).parent / "static"


def create_app(storage: EmailStorage, username: str, password: str) -> FastAPI:
    app = FastAPI(title="smtpweb")
    username_bytes = username.encode("utf-8")
    password_bytes = password.encode("utf-8")

    @app.middleware("http")
    async def require_basic_auth(request: Request, call_next):
        header = request.headers.get("authorization", "")
        if header.lower().startswith("basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                supplied_user, _, supplied_pass = decoded.partition(":")
            except Exception:
                supplied_user, supplied_pass = "", ""
            user_ok = secrets.compare_digest(supplied_user.encode("utf-8"), username_bytes)
            pass_ok = secrets.compare_digest(supplied_pass.encode("utf-8"), password_bytes)
            if user_ok and pass_ok:
                return await call_next(request)
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="smtpweb"'},
        )

    @app.get("/api/emails")
    def list_emails():
        return storage.list_emails()

    @app.get("/api/emails/{email_id}")
    def get_email(email_id: str):
        try:
            meta = storage.get_email(email_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "Email not found")
        meta = dict(meta)
        meta["text_body"] = storage.get_body_text(email_id)
        meta["html_body"] = storage.get_body_html(email_id)
        return meta

    @app.get("/api/emails/{email_id}/raw")
    def get_raw(email_id: str):
        try:
            path = storage.get_raw_path(email_id)
        except ValueError:
            raise HTTPException(400, "Invalid email id")
        if not path.exists():
            raise HTTPException(404, "Email not found")
        return FileResponse(path, media_type="message/rfc822", filename=f"{email_id}.eml")

    @app.get("/api/emails/{email_id}/attachments/{filename}")
    def get_attachment(email_id: str, filename: str):
        try:
            path = storage.get_attachment_path(email_id, filename)
        except ValueError:
            raise HTTPException(400, "Invalid attachment reference")
        if not path.exists():
            raise HTTPException(404, "Attachment not found")
        return FileResponse(path, filename=path.name)

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
