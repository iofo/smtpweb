#!/usr/bin/env python3
"""Generate a new random SMTP AUTH password and write its hash to
smtp_credentials.json, printing the plaintext once so it can be pasted
into another system's configuration.

Only a PBKDF2 hash of the password is ever stored — this is the one and
only time the plaintext is shown, so capture it now.

The running smtpweb.smtp.main process/container reads credentials once
at startup, so it must be restarted for a new password to take effect.
"""

import argparse
import json
import secrets
from pathlib import Path

from smtpweb.common.password_hashing import hash_password

DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent / "data" / "smtp"
DEFAULT_USERNAME = "smtpweb"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=DEFAULT_STATE_DIR,
        help=f"Directory containing smtp_credentials.json (default: {DEFAULT_STATE_DIR})",
    )
    parser.add_argument(
        "--username",
        help="Username to store (default: keep the existing username, or "
        f"{DEFAULT_USERNAME!r} if no credentials file exists yet)",
    )
    args = parser.parse_args()

    creds_path = args.state_dir / "smtp_credentials.json"

    username = args.username
    if username is None:
        if creds_path.exists():
            username = json.loads(creds_path.read_text())["username"]
        else:
            username = DEFAULT_USERNAME

    password = secrets.token_urlsafe(24)
    record = {"username": username, **hash_password(password)}

    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text(json.dumps(record, indent=2))
    creds_path.chmod(0o600)

    print(f"Wrote new SMTP credentials (hash only) to {creds_path}")
    print(f"username: {username}")
    print(f"password: {password}")
    print()
    print("This plaintext will not be shown again. Restart the smtp")
    print("process/container for it to take effect.")


if __name__ == "__main__":
    main()
