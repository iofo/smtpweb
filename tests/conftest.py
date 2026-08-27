from email.message import EmailMessage

import pytest
from aiosmtpd.smtp import Envelope

from smtpweb.mailbox_auth import MailboxAuth
from smtpweb.storage import EmailStorage
from smtpweb.web.app import create_app


@pytest.fixture
def mail_dir(tmp_path):
    return tmp_path / "mail"


@pytest.fixture
def storage(mail_dir):
    return EmailStorage(mail_dir)


@pytest.fixture
def web_state_dir(tmp_path):
    return tmp_path / "web"


@pytest.fixture
def mailbox_auth(web_state_dir):
    return MailboxAuth(web_state_dir)


@pytest.fixture
def app_client(storage, mailbox_auth):
    from fastapi.testclient import TestClient

    return TestClient(create_app(storage, mailbox_auth))


def make_envelope(
    mail_from="sender@example.com",
    rcpt_tos=("bob@example.com",),
    subject="Test subject",
    text="Hello, this is the body.",
    html=None,
    attachments=(),
):
    """Build a real aiosmtpd Envelope carrying a real RFC 5322 message,
    the same shape StorageHandler.handle_DATA receives."""
    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = ", ".join(rcpt_tos)
    msg["Subject"] = subject
    if text is not None:
        msg.set_content(text)
    if html is not None:
        if text is None:
            msg.set_content(html, subtype="html")
        else:
            msg.add_alternative(html, subtype="html")
    for filename, content_type, content in attachments:
        maintype, _, subtype = content_type.partition("/")
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    envelope = Envelope()
    envelope.mail_from = mail_from
    envelope.rcpt_tos = list(rcpt_tos)
    envelope.content = msg.as_bytes()
    envelope.original_content = envelope.content
    return envelope
