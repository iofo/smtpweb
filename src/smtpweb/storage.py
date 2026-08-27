import email
import email.policy
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from smtpweb.mailbox import sanitize_mailbox_name


class EmailStorage:
    """Persists received messages under `mail_dir`, one subdirectory per
    recipient mailbox, one directory per email within it:

    <mail_dir>/<mailbox>/emails/<id>/raw.eml
    <mail_dir>/<mailbox>/emails/<id>/metadata.json
    <mail_dir>/<mailbox>/emails/<id>/body.txt         (if text/plain exists)
    <mail_dir>/<mailbox>/emails/<id>/body.html        (if text/html exists)
    <mail_dir>/<mailbox>/emails/<id>/attachments/<filename>

    A message addressed to multiple recipients is stored as a full copy
    under each recipient's mailbox.
    """

    def __init__(self, mail_dir: Path):
        self.mail_dir = Path(mail_dir)
        try:
            self.mail_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # e.g. a read-only mount before the writer side has created it
            pass

    def save_message(self, envelope) -> list[dict]:
        raw_bytes = getattr(envelope, "original_content", None) or envelope.content
        if isinstance(raw_bytes, str):
            raw_bytes = raw_bytes.encode("utf-8")

        msg = email.message_from_bytes(raw_bytes, policy=email.policy.default)
        email_id = str(uuid.uuid4())

        text_body = msg.get_body(preferencelist=("plain",))
        html_body = msg.get_body(preferencelist=("html",))
        text_content = text_body.get_content() if text_body is not None else None
        html_content = html_body.get_content() if html_body is not None else None

        attachments_data = []
        used_names = set()
        for part in msg.iter_attachments():
            filename = part.get_filename() or f"attachment-{len(attachments_data) + 1}"
            filename = self._dedupe_filename(filename, used_names)
            used_names.add(filename)

            content = part.get_content()
            if isinstance(content, str):
                charset = part.get_content_charset() or "utf-8"
                content = content.encode(charset, errors="replace")
            attachments_data.append((filename, part.get_content_type(), content))

        results = []
        for recipient in envelope.rcpt_tos:
            try:
                mailbox = sanitize_mailbox_name(recipient)
            except ValueError:
                # Already validated at RCPT TO time; defensive only.
                continue

            email_dir = self.mail_dir / mailbox / "emails" / email_id
            email_dir.mkdir(parents=True, exist_ok=True)
            (email_dir / "raw.eml").write_bytes(raw_bytes)

            if text_content is not None:
                (email_dir / "body.txt").write_text(
                    text_content, encoding="utf-8", errors="replace"
                )
            if html_content is not None:
                (email_dir / "body.html").write_text(
                    html_content, encoding="utf-8", errors="replace"
                )

            attachments_meta = []
            if attachments_data:
                att_dir = email_dir / "attachments"
                att_dir.mkdir(exist_ok=True)
                for filename, content_type, content in attachments_data:
                    (att_dir / filename).write_bytes(content)
                    attachments_meta.append(
                        {"filename": filename, "content_type": content_type, "size": len(content)}
                    )

            metadata = {
                "id": email_id,
                "mailbox": mailbox,
                "message_id": msg.get("Message-ID"),
                "subject": msg.get("Subject", "(no subject)"),
                "from": msg.get("From", envelope.mail_from or ""),
                "to": list(envelope.rcpt_tos),
                "mail_from": envelope.mail_from,
                "date": msg.get("Date"),
                "received_at": datetime.now(timezone.utc).isoformat(),
                "size_bytes": len(raw_bytes),
                "has_text_body": text_content is not None,
                "has_html_body": html_content is not None,
                "attachments": attachments_meta,
            }
            (email_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
            results.append(metadata)

        return results

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

    def list_emails(self, mailbox: str) -> list[dict]:
        mailbox = sanitize_mailbox_name(mailbox)
        emails = []
        for meta_path in (self.mail_dir / mailbox / "emails").glob("*/metadata.json"):
            try:
                emails.append(json.loads(meta_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        emails.sort(key=lambda m: m.get("received_at", ""), reverse=True)
        return emails

    def get_email(self, mailbox: str, email_id: str) -> dict:
        meta_path = self._email_dir(mailbox, email_id) / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(email_id)
        return json.loads(meta_path.read_text())

    def get_body_text(self, mailbox: str, email_id: str) -> str | None:
        path = self._email_dir(mailbox, email_id) / "body.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_body_html(self, mailbox: str, email_id: str) -> str | None:
        path = self._email_dir(mailbox, email_id) / "body.html"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_raw_path(self, mailbox: str, email_id: str) -> Path:
        return self._email_dir(mailbox, email_id) / "raw.eml"

    def get_attachment_path(self, mailbox: str, email_id: str, filename: str) -> Path:
        safe_name = Path(filename).name
        if not safe_name or safe_name in (".", ".."):
            raise ValueError("Invalid filename")
        return self._email_dir(mailbox, email_id) / "attachments" / safe_name

    def _email_dir(self, mailbox: str, email_id: str) -> Path:
        mailbox = sanitize_mailbox_name(mailbox)
        safe_id = Path(email_id).name
        if not safe_id or safe_id in (".", ".."):
            raise ValueError("Invalid email id")
        return self.mail_dir / mailbox / "emails" / safe_id
