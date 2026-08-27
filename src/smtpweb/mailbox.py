import re

_MAILBOX_PATTERN = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+$")
_MAX_ADDRESS_LENGTH = 254  # RFC 5321 4.5.3.1.3: max length of a reverse/forward path


def sanitize_mailbox_name(address: str) -> str:
    """Normalize an email address into a safe, unique mailbox/directory
    name. Raises ValueError if it doesn't look like an email address —
    this is what keeps a crafted recipient/username from escaping the
    mailbox directory (e.g. "../../etc"), and the length cap keeps an
    oversized recipient from being accepted at RCPT TO only to fail later
    at the filesystem layer after a client has already sent the message."""
    address = address.strip().lower()
    if (
        not address
        or len(address) > _MAX_ADDRESS_LENGTH
        or ".." in address
        or not _MAILBOX_PATTERN.match(address)
    ):
        raise ValueError(f"Invalid mailbox address: {address!r}")
    return address
