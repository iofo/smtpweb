import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Fields use default_factory (not `= os.environ.get(...)`) so the
    # environment is read when Settings() is instantiated, not once at
    # module import — otherwise setting env vars after import (e.g. in
    # tests) would silently have no effect.
    smtp_host: str = field(default_factory=lambda: os.environ.get("SMTPWEB_SMTP_HOST", "0.0.0.0"))
    smtp_port: int = field(default_factory=lambda: int(os.environ.get("SMTPWEB_SMTP_PORT", "1025")))
    smtp_username: str | None = field(
        default_factory=lambda: os.environ.get("SMTPWEB_SMTP_USERNAME")
    )
    smtp_password: str | None = field(
        default_factory=lambda: os.environ.get("SMTPWEB_SMTP_PASSWORD")
    )
    web_host: str = field(default_factory=lambda: os.environ.get("SMTPWEB_WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.environ.get("SMTPWEB_WEB_PORT", "8080")))
    # Self-signed HTTPS is on by default — turning it off is meant for
    # local testing/debugging (e.g. browser automation can't click
    # through a self-signed-cert warning page) or when a TLS-terminating
    # proxy already sits in front and plain HTTP between it and this
    # container is an accepted trade-off. The session cookie's Secure
    # flag tracks this automatically (see web/main.py) — never manually
    # force Secure on independent of this setting, or the cookie won't
    # be sent back at all when TLS is off.
    web_tls_enabled: bool = field(default_factory=lambda: _env_bool("SMTPWEB_WEB_TLS", True))
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
    # Set at image build time (see Dockerfile's GIT_SHA build arg and the
    # publish job in .github/workflows/docker.yml) so the running web UI
    # can show which commit it was built from. "dev" for a local build
    # with no build-arg passed.
    git_sha: str = field(default_factory=lambda: os.environ.get("SMTPWEB_GIT_SHA", "dev"))
