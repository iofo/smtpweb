import email
import email.policy
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from smtpweb.common.mailbox import sanitize_mailbox_name
from smtpweb.common.pdf_thumbnail import generate_pdf_thumbnail
from smtpweb.common.security import PRIVATE_FILE_MODE


class EmailStorage:
    """Persists received messages under `mail_dir`, one subdirectory per
    recipient mailbox, one directory per email within it:

    <mail_dir>/<mailbox>/emails/<id>/raw.eml
    <mail_dir>/<mailbox>/emails/<id>/metadata.json
    <mail_dir>/<mailbox>/emails/<id>/body.txt         (if text/plain exists)
    <mail_dir>/<mailbox>/emails/<id>/body.html        (if text/html exists)
    <mail_dir>/<mailbox>/emails/<id>/attachments/<filename>
    <mail_dir>/<mailbox>/emails/<id>/attachments/thumbnails/<filename>.png
                                                       (PDF attachments only)

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
        # mailbox -> (emails_dir mtime_ns at last read, its sorted email list).
        # metadata.json files are write-once (never edited after creation),
        # so the only way list_emails()'s result can go stale is a new (or
        # removed) <email-id> subdirectory — which always bumps the parent
        # emails/ directory's own mtime. That makes one cheap stat() enough
        # to know whether the full glob+parse+sort below can be skipped.
        # Safe across the smtp/web process split too: both stat the same
        # bind-mounted directory, so a write from the smtp process is
        # visible to the web process's very next list_emails() call.
        self._list_cache: dict[str, tuple[int, list[dict]]] = {}

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
            self._write_private(email_dir / "raw.eml", raw_bytes)

            if text_content is not None:
                self._write_private(
                    email_dir / "body.txt", text_content.encode("utf-8", errors="replace")
                )
            if html_content is not None:
                self._write_private(
                    email_dir / "body.html", html_content.encode("utf-8", errors="replace")
                )

            attachments_meta = []
            if attachments_data:
                att_dir = email_dir / "attachments"
                att_dir.mkdir(exist_ok=True)
                for filename, content_type, content in attachments_data:
                    att_path = att_dir / filename
                    self._write_private(att_path, content)

                    has_thumbnail = False
                    if filename.lower().endswith(".pdf"):
                        thumb_path = att_dir / "thumbnails" / f"{filename}.png"
                        has_thumbnail = generate_pdf_thumbnail(att_path, thumb_path)

                    attachments_meta.append(
                        {
                            "filename": filename,
                            "content_type": content_type,
                            "size": len(content),
                            "has_thumbnail": has_thumbnail,
                        }
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
            self._write_private(
                email_dir / "metadata.json", json.dumps(metadata, indent=2).encode("utf-8")
            )
            results.append(metadata)

        return results

    @staticmethod
    def _write_private(path: Path, data: bytes) -> None:
        """Write data to path and restrict it to owner read/write — every
        email file (body, attachment, metadata) may hold sensitive content
        (e.g. a scanned document), not just the credential files that
        already got this treatment."""
        path.write_bytes(data)
        path.chmod(PRIVATE_FILE_MODE)

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
        emails_dir = self.mail_dir / mailbox / "emails"
        try:
            current_mtime_ns = emails_dir.stat().st_mtime_ns
        except OSError:
            return []

        cached = self._list_cache.get(mailbox)
        if cached is not None and cached[0] == current_mtime_ns:
            return cached[1]

        emails = []
        for meta_path in emails_dir.glob("*/metadata.json"):
            try:
                emails.append(json.loads(meta_path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        emails.sort(key=lambda m: m.get("received_at", ""), reverse=True)

        self._list_cache[mailbox] = (current_mtime_ns, emails)
        return emails

    def get_email(self, mailbox: str, email_id: str) -> dict:
        meta_path = self._email_dir(mailbox, email_id) / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(email_id)
        return json.loads(meta_path.read_text())

    def delete_email(self, mailbox: str, email_id: str) -> None:
        """Permanently remove an email and everything under it (body,
        attachments, thumbnails). Raises FileNotFoundError if it doesn't
        exist. Removing the <email-id> directory changes the parent
        emails/ directory's own mtime the same way creating one does, so
        list_emails()'s cache invalidates correctly with no extra work."""
        email_dir = self._email_dir(mailbox, email_id)
        if not email_dir.is_dir():
            raise FileNotFoundError(email_id)
        shutil.rmtree(email_dir)

    def get_body_text(self, mailbox: str, email_id: str) -> str | None:
        path = self._email_dir(mailbox, email_id) / "body.txt"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_body_html(self, mailbox: str, email_id: str) -> str | None:
        path = self._email_dir(mailbox, email_id) / "body.html"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_raw_path(self, mailbox: str, email_id: str) -> Path:
        return self._email_dir(mailbox, email_id) / "raw.eml"

    def get_attachment_path(self, mailbox: str, email_id: str, filename: str) -> Path:
        safe_name = self._safe_component(filename, "filename")
        return self._email_dir(mailbox, email_id) / "attachments" / safe_name

    def get_attachment_thumbnail_path(self, mailbox: str, email_id: str, filename: str) -> Path:
        safe_name = self._safe_component(filename, "filename")
        return (
            self._email_dir(mailbox, email_id) / "attachments" / "thumbnails" / f"{safe_name}.png"
        )

    def _email_dir(self, mailbox: str, email_id: str) -> Path:
        mailbox = sanitize_mailbox_name(mailbox)
        safe_id = self._safe_component(email_id, "email id")
        return self.mail_dir / mailbox / "emails" / safe_id

    @staticmethod
    def _safe_component(value: str, label: str) -> str:
        """Reduce a client-supplied path segment (filename or email id) to
        its basename and reject anything that could escape the intended
        directory once joined onto a Path."""
        safe = Path(value).name
        if not safe or safe in (".", ".."):
            raise ValueError(f"Invalid {label}")
        return safe
