#!/usr/bin/env python3
"""Generate a new random SMTP AUTH password and write it to
smtp_credentials.json, printing the plaintext so it can be pasted into
another system's configuration.

The SMTP AUTH credential is a single shared service credential (not a
personal password), so unlike the per-mailbox web logins it's stored in
plaintext by design — see README > Authentication.

The running smtp_main process/container reads credentials once at
startup, so it must be restarted for a new password to take effect.
"""

import argparse
import json
import secrets
from pathlib import Path

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

    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text(json.dumps({"username": username, "password": password}, indent=2))
    creds_path.chmod(0o600)

    print(f"Wrote new SMTP credentials to {creds_path}")
    print(f"username: {username}")
    print(f"password: {password}")
    print()
    print("Restart the smtp_main process/container for this to take effect.")


if __name__ == "__main__":
    main()
