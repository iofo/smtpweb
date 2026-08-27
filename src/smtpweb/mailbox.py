import re

_MAILBOX_PATTERN = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+$")


def sanitize_mailbox_name(address: str) -> str:
    """Normalize an email address into a safe, unique mailbox/directory
    name. Raises ValueError if it doesn't look like an email address —
    this is what keeps a crafted recipient/username from escaping the
    mailbox directory (e.g. "../../etc")."""
    address = address.strip().lower()
    if not address or ".." in address or not _MAILBOX_PATTERN.match(address):
        raise ValueError(f"Invalid mailbox address: {address!r}")
    return address
