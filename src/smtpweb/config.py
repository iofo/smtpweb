import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    smtp_host: str = os.environ.get("SMTPWEB_SMTP_HOST", "0.0.0.0")
    smtp_port: int = int(os.environ.get("SMTPWEB_SMTP_PORT", "1025"))
    smtp_username: str | None = os.environ.get("SMTPWEB_SMTP_USERNAME")
    smtp_password: str | None = os.environ.get("SMTPWEB_SMTP_PASSWORD")
    web_host: str = os.environ.get("SMTPWEB_WEB_HOST", "0.0.0.0")
    web_port: int = int(os.environ.get("SMTPWEB_WEB_PORT", "8080"))
    # Shared: received mail, one subdirectory per recipient mailbox.
    # Mount read-write for smtp_main, read-only for web_main.
    mail_dir: Path = Path(os.environ.get("SMTPWEB_MAIL_DIR", "./data/mail"))
    # smtp_main-only: SMTP AUTH credentials + TLS cert/key. Not needed by,
    # and should not be mounted into, the web process.
    smtp_state_dir: Path = Path(os.environ.get("SMTPWEB_SMTP_STATE_DIR", "./data/smtp"))
    # web_main-only: per-mailbox web login credentials. Not needed by, and
    # should not be mounted into, the smtp process.
    web_state_dir: Path = Path(os.environ.get("SMTPWEB_WEB_STATE_DIR", "./data/web"))
