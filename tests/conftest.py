from email.message import EmailMessage

import pytest
from aiosmtpd.smtp import Envelope

from smtpweb.common.storage import EmailStorage
from smtpweb.web.app import create_app
from smtpweb.web.mailbox_auth import MailboxAuth

# A real, minimal-but-valid single-page PDF (the classic minimal-PDF
# example), used wherever tests need actual PDF bytes a renderer can
# open — not just something merely named ".pdf".
MINIMAL_PDF_BYTES = b"""%PDF-1.1
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 300 144] /Contents 5 0 R >> endobj
4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >> endobj
5 0 obj << /Length 73 >>
stream
BT
/F1 18 Tf
0 0 Td
(Hello World) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f
0000000018 00000 n
0000000077 00000 n
0000000178 00000 n
0000000457 00000 n
0000000536 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
649
%%EOF"""


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


@pytest.fixture
def secure_app_client(storage, mailbox_auth):
    """Same as app_client, but built the way web_main does when
    SMTPWEB_WEB_TLS is enabled (cookie_secure=True)."""
    from fastapi.testclient import TestClient

    return TestClient(create_app(storage, mailbox_auth, cookie_secure=True))


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
