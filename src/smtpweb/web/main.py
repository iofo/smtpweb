import logging

import uvicorn

from smtpweb.common.config import Settings
from smtpweb.common.logging_config import configure_logging
from smtpweb.common.storage import EmailStorage
from smtpweb.common.tls import ensure_self_signed_cert
from smtpweb.web.app import create_app
from smtpweb.web.mailbox_auth import MailboxAuth

log = logging.getLogger(__name__)


def run():
    configure_logging()

    settings = Settings()
    storage = EmailStorage(settings.mail_dir)
    mailbox_auth = MailboxAuth(settings.web_state_dir)

    uvicorn_tls_kwargs = {}
    scheme = "http"
    if settings.web_tls_enabled:
        cert_path, key_path = ensure_self_signed_cert(settings.web_state_dir / "tls")
        uvicorn_tls_kwargs = {"ssl_certfile": str(cert_path), "ssl_keyfile": str(key_path)}
        scheme = "https"
        log.info(
            "Presenting a self-signed certificate — browsers will warn on first visit; "
            "put a trusted TLS-terminating proxy in front for anything beyond that"
        )
    else:
        log.warning(
            "SMTPWEB_WEB_TLS=false — serving plain HTTP. Login passwords and session "
            "cookies will cross the network unencrypted. Only use this for local "
            "testing/debugging, or behind a proxy that already terminates TLS."
        )

    log.info("Web UI listening on %s://%s:%s", scheme, settings.web_host, settings.web_port)
    log.info("Running from commit %s", settings.git_sha)
    log.info(
        "Log in with a recipient's email address as the username — the "
        "password entered the first time for a given mailbox becomes its "
        "password from then on"
    )

    uvicorn.run(
        create_app(
            storage,
            mailbox_auth,
            cookie_secure=settings.web_tls_enabled,
            git_sha=settings.git_sha,
        ),
        host=settings.web_host,
        port=settings.web_port,
        **uvicorn_tls_kwargs,
    )


if __name__ == "__main__":
    run()
