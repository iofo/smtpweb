import email
import email.policy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path


class EmailStorage:
    """Persists received messages under `base_dir`, one directory per email:

    <base_dir>/<id>/raw.eml
    <base_dir>/<id>/metadata.json
    <base_dir>/<id>/body.txt         (if a text/plain part exists)
    <base_dir>/<id>/body.html        (if a text/html part exists)
    <base_dir>/<id>/attachments/<filename>
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_message(self, envelope) -> dict:
        raw_bytes = getattr(envelope, "original_content", None) or envelope.content
        if isinstance(raw_bytes, str):
            raw_bytes = raw_bytes.encode("utf-8")

        msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)

        email_id = str(uuid.uuid4())
        email_dir = self.base_dir / email_id
        email_dir.mkdir(parents=True)
        (email_dir / "raw.eml").write_bytes(raw_bytes)

        text_body = msg.get_body(preferencelist=("plain",))
        html_body = msg.get_body(preferencelist=("html",))

        if text_body is not None:
            (email_dir / "body.txt").write_text(
                text_body.get_content(), encoding="utf-8", errors="replace"
            )
        if html_body is not None:
            (email_dir / "body.html").write_text(
                html_body.get_content(), encoding="utf-8", errors="replace"
            )

        attachments = []
        used_names = set()
        for part in msg.iter_attachments():
            filename = part.get_filename() or f"attachment-{len(attachments) + 1}"
            filename = self._dedupe_filename(filename, used_names)
            used_names.add(filename)

            content = part.get_content()
            if isinstance(content, str):
                charset = part.get_content_charset() or "utf-8"
                content = content.encode(charset, errors="replace")

            att_dir = email_dir / "attachments"
            att_dir.mkdir(exist_ok=True)
            (att_dir / filename).write_bytes(content)

            attachments.append(
                {
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "size": len(content),
                }
            )

        metadata = {
            "id": email_id,
            "message_id": msg.get("Message-ID"),
            "subject": msg.get("Subject", "(no subject)"),
            "from": msg.get("From", envelope.mail_from or ""),
            "to": list(envelope.rcpt_tos),
            "mail_from": envelope.mail_from,
            "date": msg.get("Date"),
            "received_at": datetime.now(timezone.utc).isoformat(),
            "size_bytes": len(raw_bytes),
            "has_text_body": text_body is not None,
            "has_html_body": html_body is not None,
            "attachments": attachments,
        }
        (email_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        return metadata

    @staticmethod
    def _dedupe_filename(filename: str, used_names: set) -> str:
        filename = Path(filename).name  # strip any directory components
        if filename not in used_names:
            return filename
        stem, _, suffix = filename.rpartition(".")
        base = stem if stem else filename
        suffix = f".{suffix}" if stem else ""
        n = 2
        while f"{base}-{n}{suffix}" in used_names:
            n += 1
        return f"{base}-{n}{suffix}"

    def list_emails(self) -> list[dict]:
        emails = []
        for meta_path in self.base_dir.glob("*/metadata.json"):
            try:
                emails.append(json.loads(meta_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        emails.sort(key=lambda m: m.get("received_at", ""), reverse=True)
        return emails

    def get_email(self, email_id: str) -> dict:
        meta_path = self._safe_email_dir(email_id) / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(email_id)
        return json.loads(meta_path.read_text())

    def get_body_text(self, email_id: str) -> str | None:
        path = self._safe_email_dir(email_id) / "body.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_body_html(self, email_id: str) -> str | None:
        path = self._safe_email_dir(email_id) / "body.html"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_raw_path(self, email_id: str) -> Path:
        return self._safe_email_dir(email_id) / "raw.eml"

    def get_attachment_path(self, email_id: str, filename: str) -> Path:
        safe_name = Path(filename).name
        if not safe_name or safe_name in (".", ".."):
            raise ValueError("Invalid filename")
        return self._safe_email_dir(email_id) / "attachments" / safe_name

    def _safe_email_dir(self, email_id: str) -> Path:
        safe_id = Path(email_id).name
        if not safe_id or safe_id in (".", ".."):
            raise ValueError("Invalid email id")
        return self.base_dir / safe_id
