import logging

import uvicorn

from smtpweb.common.config import Settings
from smtpweb.common.logging_config import configure_logging
from smtpweb.common.storage import EmailStorage
from smtpweb.common.tls import build_tls_context, ensure_self_signed_cert
from smtpweb.web.app import create_app
from smtpweb.web.mailbox_auth import MailboxAuth

log = logging.getLogger(__name__)


def run():
    configure_logging()

    settings = Settings()
    storage = EmailStorage(settings.mail_dir)
    mailbox_auth = MailboxAuth(settings.web_state_dir)

    cert_path, key_path = ensure_self_signed_cert(settings.web_state_dir / "tls")

    log.info("Web UI listening on https://%s:%s", settings.web_host, settings.web_port)
    log.info(
        "Presenting a self-signed certificate — browsers will warn on first visit; "
        "put a trusted TLS-terminating proxy in front for anything beyond that"
    )
    log.info(
        "Log in with a recipient's email address as the username — the "
        "password entered the first time for a given mailbox becomes its "
        "password from then on"
    )

    uvicorn.run(
        create_app(storage, mailbox_auth),
        host=settings.web_host,
        port=settings.web_port,
        ssl_certfile=str(cert_path),
        ssl_keyfile=str(key_path),
    )


if __name__ == "__main__":
    run()
