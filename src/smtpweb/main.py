import logging

import uvicorn

from smtpweb.config import Settings
from smtpweb.smtp_server import build_controller
from smtpweb.storage import EmailStorage
from smtpweb.web.app import create_app

log = logging.getLogger(__name__)


def run():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    settings = Settings()
    storage = EmailStorage(settings.data_dir)

    controller = build_controller(storage, settings.smtp_host, settings.smtp_port)
    controller.start()
    log.info("SMTP server listening on %s:%s", settings.smtp_host, settings.smtp_port)
    log.info("Storing emails under %s", settings.data_dir.resolve())

    try:
        log.info("Web UI listening on %s:%s", settings.web_host, settings.web_port)
        uvicorn.run(create_app(storage), host=settings.web_host, port=settings.web_port)
    finally:
        controller.stop()


if __name__ == "__main__":
    run()
