import logging

import uvicorn

from smtpweb.auth import Authenticator, resolve_credentials
from smtpweb.config import Settings
from smtpweb.smtp_server import build_controller
from smtpweb.storage import EmailStorage
from smtpweb.tls import build_tls_context, ensure_self_signed_cert
from smtpweb.web.app import create_app

log = logging.getLogger(__name__)


def run():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    settings = Settings()
    storage = EmailStorage(settings.data_dir)

    creds_path = settings.data_dir.parent / "smtp_credentials.json"
    username, password, generated = resolve_credentials(
        creds_path, settings.smtp_username, settings.smtp_password
    )
    authenticator = Authenticator(username, password)

    cert_path, key_path = ensure_self_signed_cert(settings.data_dir.parent / "tls")
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
            "— using generated credentials (username=%r) stored at %s",
            username,
            creds_path,
        )
    log.info("Storing emails under %s", settings.data_dir.resolve())

    try:
        log.info("Web UI listening on %s:%s", settings.web_host, settings.web_port)
        uvicorn.run(create_app(storage), host=settings.web_host, port=settings.web_port)
    finally:
        controller.stop()


if __name__ == "__main__":
    run()
