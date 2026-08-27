import logging

import uvicorn

from smtpweb.auth import resolve_credentials
from smtpweb.config import Settings
from smtpweb.storage import EmailStorage
from smtpweb.web.app import create_app

log = logging.getLogger(__name__)


def run():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    settings = Settings()
    storage = EmailStorage(settings.data_dir)

    creds_path = settings.data_dir.parent / "web_credentials.json"
    username, password, generated = resolve_credentials(
        creds_path,
        settings.web_username,
        settings.web_password,
        ("SMTPWEB_WEB_USERNAME", "SMTPWEB_WEB_PASSWORD"),
        default_username="admin",
    )
    if generated:
        log.warning(
            "No web UI credentials configured via SMTPWEB_WEB_USERNAME/SMTPWEB_WEB_PASSWORD "
            "— using generated credentials (username=%r) stored at %s",
            username,
            creds_path,
        )
    log.info("Web UI listening on %s:%s", settings.web_host, settings.web_port)

    uvicorn.run(
        create_app(storage, username, password),
        host=settings.web_host,
        port=settings.web_port,
    )


if __name__ == "__main__":
    run()
