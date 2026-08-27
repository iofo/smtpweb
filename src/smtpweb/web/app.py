from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from smtpweb.storage import EmailStorage

STATIC_DIR = Path(__file__).parent / "static"


def create_app(storage: EmailStorage) -> FastAPI:
    app = FastAPI(title="smtpweb")

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
