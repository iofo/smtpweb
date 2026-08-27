#!/usr/bin/env python3
"""Send a handful of sample emails to a running smtpweb instance.

Authenticates over STARTTLS. Credentials are taken from --username/
--password, or SMTPWEB_SMTP_USERNAME/SMTPWEB_SMTP_PASSWORD, or (as a
fallback for local dev) the auto-generated data/smtp_credentials.json.
"""

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

DEFAULT_CREDENTIALS_FILE = (
    Path(__file__).resolve().parent.parent / "data" / "smtp_credentials.json"
)


def plain_email() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Plain text email"
    msg.set_content("Hello Bob,\n\nThis is a plain text message.\n\n-Alice")
    return msg


def html_email() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "carol@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "HTML email"
    msg.set_content("This is the plain text fallback body.")
    msg.add_alternative(
        "<h1>Hello Bob</h1><p>This is an <b>HTML</b> email with a "
        "<a href='https://example.com'>link</a>.</p>",
        subtype="html",
    )
    return msg


def attachment_email() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "dave@example.com"
    msg["To"] = "bob@example.com, eve@example.com"
    msg["Subject"] = "Email with attachments"
    msg.set_content("Please find the attached files.")
    msg.add_alternative(
        "<p>Please find the attached files.</p>",
        subtype="html",
    )
    msg.add_attachment(
        b"name,value\nfoo,1\nbar,2\n",
        maintype="text",
        subtype="csv",
        filename="data.csv",
    )
    msg.add_attachment(
        b"This is the content of a plain text attachment.\n",
        maintype="text",
        subtype="plain",
        filename="note.txt",
    )
    return msg


EMAILS = [plain_email, html_email, attachment_email]


def resolve_credentials(username_arg: str | None, password_arg: str | None):
    if username_arg and password_arg:
        return username_arg, password_arg

    env_username = os.environ.get("SMTPWEB_SMTP_USERNAME")
    env_password = os.environ.get("SMTPWEB_SMTP_PASSWORD")
    if env_username and env_password:
        return env_username, env_password

    if DEFAULT_CREDENTIALS_FILE.exists():
        data = json.loads(DEFAULT_CREDENTIALS_FILE.read_text())
        return data["username"], data["password"]

    raise SystemExit(
        "No SMTP credentials found. Pass --username/--password, set "
        "SMTPWEB_SMTP_USERNAME/SMTPWEB_SMTP_PASSWORD, or ensure "
        f"{DEFAULT_CREDENTIALS_FILE} exists."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="SMTP server host")
    parser.add_argument("--port", type=int, default=1025, help="SMTP server port")
    parser.add_argument("--username", help="SMTP AUTH username")
    parser.add_argument("--password", help="SMTP AUTH password")
    args = parser.parse_args()

    username, password = resolve_credentials(args.username, args.password)

    # The server presents a self-signed certificate for local/dev use, so
    # certificate verification is intentionally disabled here.
    tls_context = ssl.create_default_context()
    tls_context.check_hostname = False
    tls_context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP(args.host, args.port) as s:
        s.starttls(context=tls_context)
        s.login(username, password)
        for build in EMAILS:
            msg = build()
            s.send_message(msg)
            print(f"sent: {msg['Subject']!r}")


if __name__ == "__main__":
    main()
