import logging
import signal
import threading

from smtpweb.smtp.auth import Authenticator, resolve_credentials
from smtpweb.common.config import Settings
from smtpweb.common.logging_config import configure_logging
from smtpweb.smtp.server import build_controller
from smtpweb.common.storage import EmailStorage
from smtpweb.smtp.tls import build_tls_context, ensure_self_signed_cert

log = logging.getLogger(__name__)


def run():
    configure_logging()

    settings = Settings()
    storage = EmailStorage(settings.mail_dir)

    creds_path = settings.smtp_state_dir / "smtp_credentials.json"
    username, password_record, generated, new_password = resolve_credentials(
        creds_path,
        settings.smtp_username,
        settings.smtp_password,
        ("SMTPWEB_SMTP_USERNAME", "SMTPWEB_SMTP_PASSWORD"),
        default_username="smtpweb",
    )
    authenticator = Authenticator(username, password_record)

    cert_path, key_path = ensure_self_signed_cert(settings.smtp_state_dir / "tls")
    tls_context = build_tls_context(cert_path, key_path)

    controller = build_controller(
        storage, settings.smtp_host, settings.smtp_port, authenticator, tls_context
    )
    controller.start()
    log.info(
        "SMTP server listening on %s:%s (STARTTLS required for AUTH; AUTH required for mail)",
        settings.smtp_host,
        settings.smtp_port,
    )
    if generated:
        log.warning(
            "No SMTP credentials configured via SMTPWEB_SMTP_USERNAME/SMTPWEB_SMTP_PASSWORD "
            "— using credentials (username=%r) persisted at %s (password hash only; "
            "the plaintext is not recoverable from disk)",
            username,
            creds_path,
        )
    if new_password is not None:
        log.warning(
            "Generated a new SMTP password — only its hash is stored, so this is the "
            "only time it will ever be shown: %s",
            new_password,
        )
    log.info(
        "Storing mail under %s (one subdirectory per recipient mailbox)",
        settings.mail_dir.resolve(),
    )

    stop_event = threading.Event()
    signal.signal(signal.SIGTERM, lambda signum, frame: stop_event.set())
    signal.signal(signal.SIGINT, lambda signum, frame: stop_event.set())
    stop_event.wait()
    controller.stop()


if __name__ == "__main__":
    run()
