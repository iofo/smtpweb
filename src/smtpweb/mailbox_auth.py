import hashlib
import hmac
import json
import os
from pathlib import Path

from smtpweb.mailbox import sanitize_mailbox_name

PBKDF2_ITERATIONS = 310_000


def _hash_password(password: str) -> dict:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": salt.hex(),
        "hash": derived.hex(),
    }


def _verify_password(password: str, record: dict) -> bool:
    salt = bytes.fromhex(record["salt"])
    expected = bytes.fromhex(record["hash"])
    iterations = record.get("iterations", PBKDF2_ITERATIONS)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


class MailboxAuth:
    """Per-mailbox web login: the username is the recipient email address,
    and there's no separate signup step — whichever password is submitted
    the first time a given mailbox is logged into becomes that mailbox's
    password (self-service claiming), verified on every login after that.
    Passwords are never stored in plaintext or reversibly encrypted — only
    a PBKDF2-HMAC-SHA256 hash with a random per-mailbox salt is written to
    disk, verified with a constant-time comparison.

    Because claiming requires nothing but knowing the address, anyone who
    guesses/knows a mailbox address can claim it before its real owner
    does, and there's no way to prove who actually controls that address.
    That's acceptable only because this server isn't meant to be exposed
    to the internet (see README). A real deployment would need to verify
    mailbox ownership before allowing a claim or password reset — e.g.
    emailing a one-time code to that address via the SMTP side and
    requiring it back before setting a new password — which is not
    implemented here.
    """

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _creds_path(self, mailbox: str) -> Path:
        return self.state_dir / mailbox / "credentials.json"

    def login(self, username: str, password: str) -> str | None:
        """Return the normalized mailbox name on success, else None."""
        if not password:
            return None
        try:
            mailbox = sanitize_mailbox_name(username)
        except ValueError:
            return None

        path = self._creds_path(mailbox)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic exclusive create: if two logins race to claim the same
        # unclaimed mailbox, exactly one of them wins this open() and sets
        # the password; the other falls through to the verify branch below
        # and is checked against whichever password actually won the race.
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(_hash_password(password), indent=2))
            return mailbox

        try:
            record = json.loads(path.read_text())
            return mailbox if _verify_password(password, record) else None
        except (OSError, json.JSONDecodeError, KeyError, ValueError):
            return None
