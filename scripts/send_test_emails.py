#!/usr/bin/env python3
"""Send a handful of sample emails to a running smtpweb instance."""

import argparse
import smtplib
from email.message import EmailMessage


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="SMTP server host")
    parser.add_argument("--port", type=int, default=1025, help="SMTP server port")
    args = parser.parse_args()

    with smtplib.SMTP(args.host, args.port) as s:
        for build in EMAILS:
            msg = build()
            s.send_message(msg)
            print(f"sent: {msg['Subject']!r}")


if __name__ == "__main__":
    main()
