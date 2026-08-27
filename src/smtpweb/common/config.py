import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    # Fields use default_factory (not `= os.environ.get(...)`) so the
    # environment is read when Settings() is instantiated, not once at
    # module import — otherwise setting env vars after import (e.g. in
    # tests) would silently have no effect.
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTPWEB_SMTP_HOST", "0.0.0.0"))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTPWEB_SMTP_PORT", "1025")))
    smtp_username: str | None = field(default_factory=lambda: os.environ.get("SMTPWEB_SMTP_USERNAME"))
    smtp_password: str | None = field(default_factory=lambda: os.environ.get("SMTPWEB_SMTP_PASSWORD"))
    web_host: str = field(default_factory=lambda: os.environ.get("SMTPWEB_WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.environ.get("SMTPWEB_WEB_PORT", "8080")))
    # Shared: received mail, one subdirectory per recipient mailbox.
    # Read-write for both processes — smtp_main only ever creates new
    # <email-id> directories and never touches one again afterward, so
    # there's no write/write race with web_main deleting an existing one.
    mail_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("SMTPWEB_MAIL_DIR", "./data/mail"))
    )
    # smtp_main-only: SMTP AUTH credentials + TLS cert/key. Not needed by,
    # and should not be mounted into, the web process.
    smtp_state_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("SMTPWEB_SMTP_STATE_DIR", "./data/smtp"))
    )
    # web_main-only: per-mailbox web login credentials + its own TLS
    # cert/key. Not needed by, and should not be mounted into, the smtp
    # process.
    web_state_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("SMTPWEB_WEB_STATE_DIR", "./data/web"))
    )
