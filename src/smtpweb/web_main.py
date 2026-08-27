import logging

import uvicorn

from smtpweb.config import Settings
from smtpweb.mailbox_auth import MailboxAuth
from smtpweb.storage import EmailStorage
from smtpweb.web.app import create_app

log = logging.getLogger(__name__)


def run():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    settings = Settings()
    storage = EmailStorage(settings.mail_dir)
    mailbox_auth = MailboxAuth(settings.web_state_dir)

    log.info("Web UI listening on %s:%s", settings.web_host, settings.web_port)
    log.info(
        "Log in with a recipient's email address as the username — the "
        "password entered the first time for a given mailbox becomes its "
        "password from then on"
    )

    uvicorn.run(
        create_app(storage, mailbox_auth), host=settings.web_host, port=settings.web_port
    )


if __name__ == "__main__":
    run()
