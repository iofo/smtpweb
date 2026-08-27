import logging
import ssl

from aiosmtpd.controller import Controller

from smtpweb.auth import Authenticator
from smtpweb.storage import EmailStorage

log = logging.getLogger(__name__)


class StorageHandler:
    """aiosmtpd handler that accepts any sender/recipient and persists
    every message it receives via EmailStorage."""

    def __init__(self, storage: EmailStorage):
        self.storage = storage

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        try:
            metadata = self.storage.save_message(envelope)
        except Exception:
            log.exception("Failed to store incoming message")
            return "451 Requested action aborted: error in processing"
        log.info(
            "Received message %s from %s to %s (%d bytes)",
            metadata["id"],
            metadata["mail_from"],
            metadata["to"],
            metadata["size_bytes"],
        )
        return "250 Message accepted for delivery"


def build_controller(
    storage: EmailStorage,
    host: str,
    port: int,
    authenticator: Authenticator,
    tls_context: ssl.SSLContext,
) -> Controller:
    handler = StorageHandler(storage)
    return Controller(
        handler,
        hostname=host,
        port=port,
        authenticator=authenticator,
        auth_required=True,
        auth_require_tls=True,
        tls_context=tls_context,
    )
