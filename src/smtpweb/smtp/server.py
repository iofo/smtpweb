import logging
import ssl

from aiosmtpd.controller import Controller

from smtpweb.common.mailbox import sanitize_mailbox_name
from smtpweb.common.storage import EmailStorage
from smtpweb.smtp.auth import Authenticator

log = logging.getLogger(__name__)


class StorageHandler:
    """aiosmtpd handler that accepts mail for any syntactically valid
    recipient and persists a copy into each recipient's mailbox via
    EmailStorage."""

    def __init__(self, storage: EmailStorage):
        self.storage = storage

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        try:
            sanitize_mailbox_name(address)
        except ValueError:
            return "553 5.1.3 Bad recipient address syntax"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        try:
            results = self.storage.save_message(envelope)
        except Exception:
            log.exception("Failed to store incoming message")
            return "451 Requested action aborted: error in processing"
        for metadata in results:
            log.info(
                "Stored message %s in mailbox %s from %s (%d bytes)",
                metadata["id"],
                metadata["mailbox"],
                metadata["mail_from"],
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
