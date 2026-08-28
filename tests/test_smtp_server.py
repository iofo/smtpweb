import asyncio

from aiosmtpd.smtp import Envelope

from smtpweb.smtp.server import StorageHandler

from .conftest import make_envelope


def run(coro):
    return asyncio.run(coro)


class FakeStorage:
    def __init__(self):
        self.saved = []
        self.raise_on_save = False

    def save_message(self, envelope):
        if self.raise_on_save:
            raise RuntimeError("boom")
        result = [
            {
                "id": "fake-id",
                "mailbox": "bob@example.com",
                "mail_from": envelope.mail_from,
                "size_bytes": 1,
            }
        ]
        self.saved.append(envelope)
        return result


def test_handle_rcpt_accepts_valid_address():
    handler = StorageHandler(FakeStorage())
    envelope = Envelope()
    response = run(handler.handle_RCPT(None, None, envelope, "bob@example.com", {}))
    assert response == "250 OK"
    assert envelope.rcpt_tos == ["bob@example.com"]


def test_handle_rcpt_rejects_invalid_address():
    handler = StorageHandler(FakeStorage())
    envelope = Envelope()
    response = run(handler.handle_RCPT(None, None, envelope, "not-an-email", {}))
    assert response == "553 5.1.3 Bad recipient address syntax"
    assert envelope.rcpt_tos == []


def test_handle_rcpt_rejects_oversized_address():
    handler = StorageHandler(FakeStorage())
    envelope = Envelope()
    huge = "a" * 300 + "@example.com"
    response = run(handler.handle_RCPT(None, None, envelope, huge, {}))
    assert response == "553 5.1.3 Bad recipient address syntax"


def test_handle_data_stores_and_accepts():
    fake_storage = FakeStorage()
    handler = StorageHandler(fake_storage)
    envelope = make_envelope()
    response = run(handler.handle_DATA(None, None, envelope))
    assert response == "250 Message accepted for delivery"
    assert len(fake_storage.saved) == 1


def test_handle_data_returns_error_on_storage_failure():
    fake_storage = FakeStorage()
    fake_storage.raise_on_save = True
    handler = StorageHandler(fake_storage)
    envelope = make_envelope()
    response = run(handler.handle_DATA(None, None, envelope))
    assert response == "451 Requested action aborted: error in processing"


def test_handle_data_uses_real_storage(storage):
    handler = StorageHandler(storage)
    envelope = make_envelope(rcpt_tos=("bob@example.com", "eve@example.com"))
    response = run(handler.handle_DATA(None, None, envelope))
    assert response == "250 Message accepted for delivery"
    assert len(storage.list_emails("bob@example.com")) == 1
    assert len(storage.list_emails("eve@example.com")) == 1
