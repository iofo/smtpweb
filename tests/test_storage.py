import pytest

from .conftest import make_envelope


def test_save_message_creates_mailbox_and_files(storage, mail_dir):
    results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
    assert len(results) == 1
    meta = results[0]
    assert meta["mailbox"] == "bob@example.com"

    email_dir = mail_dir / "bob@example.com" / "emails" / meta["id"]
    assert (email_dir / "raw.eml").exists()
    assert (email_dir / "metadata.json").exists()
    assert (email_dir / "body.txt").read_text().strip() == "Hello, this is the body."


def test_save_message_writes_html_body(storage):
    results = storage.save_message(
        make_envelope(text="plain part", html="<p>html part</p>")
    )
    meta = results[0]
    html = storage.get_body_html(meta["mailbox"], meta["id"])
    text = storage.get_body_text(meta["mailbox"], meta["id"])
    assert "html part" in html
    assert "plain part" in text


def test_save_message_writes_attachments(storage):
    results = storage.save_message(
        make_envelope(attachments=[("note.txt", "text/plain", b"attachment bytes")])
    )
    meta = results[0]
    assert len(meta["attachments"]) == 1
    att = meta["attachments"][0]
    assert att["filename"] == "note.txt"
    assert att["content_type"] == "text/plain"
    assert att["size"] == len(b"attachment bytes")

    path = storage.get_attachment_path(meta["mailbox"], meta["id"], "note.txt")
    assert path.read_bytes() == b"attachment bytes"


def test_multi_recipient_message_stored_under_each_mailbox(storage):
    results = storage.save_message(
        make_envelope(rcpt_tos=("bob@example.com", "eve@example.com"))
    )
    assert len(results) == 2
    mailboxes = {r["mailbox"] for r in results}
    assert mailboxes == {"bob@example.com", "eve@example.com"}
    # Same message -> same email id shared across both mailboxes' copies.
    ids = {r["id"] for r in results}
    assert len(ids) == 1


def test_recipient_only_sees_their_own_mail(storage):
    storage.save_message(make_envelope(rcpt_tos=("bob@example.com",), subject="For Bob"))
    storage.save_message(make_envelope(rcpt_tos=("eve@example.com",), subject="For Eve"))

    bob_subjects = {e["subject"] for e in storage.list_emails("bob@example.com")}
    eve_subjects = {e["subject"] for e in storage.list_emails("eve@example.com")}
    assert bob_subjects == {"For Bob"}
    assert eve_subjects == {"For Eve"}


def test_list_emails_sorted_newest_first(storage):
    storage.save_message(make_envelope(subject="first"))
    storage.save_message(make_envelope(subject="second"))
    emails = storage.list_emails("bob@example.com")
    received_ats = [e["received_at"] for e in emails]
    assert received_ats == sorted(received_ats, reverse=True)


def test_list_emails_empty_for_unknown_mailbox(storage):
    assert storage.list_emails("nobody@example.com") == []


def test_get_email_raises_for_missing_id(storage):
    storage.save_message(make_envelope())
    with pytest.raises(FileNotFoundError):
        storage.get_email("bob@example.com", "00000000-0000-0000-0000-000000000000")


def test_get_attachment_path_rejects_path_traversal_filename(storage):
    results = storage.save_message(make_envelope())
    meta = results[0]
    with pytest.raises(ValueError):
        storage.get_attachment_path(meta["mailbox"], meta["id"], "..")


def test_get_attachment_path_strips_directory_components(storage):
    results = storage.save_message(
        make_envelope(attachments=[("note.txt", "text/plain", b"x")])
    )
    meta = results[0]
    # A filename smuggling a parent-directory traversal must resolve to
    # just the basename within this email's own attachments dir, never
    # escape it.
    path = storage.get_attachment_path(meta["mailbox"], meta["id"], "../../../etc/note.txt")
    assert path == storage.get_attachment_path(meta["mailbox"], meta["id"], "note.txt")


def test_duplicate_attachment_filenames_are_deduped(storage):
    results = storage.save_message(
        make_envelope(
            attachments=[
                ("note.txt", "text/plain", b"first"),
                ("note.txt", "text/plain", b"second"),
            ]
        )
    )
    filenames = [a["filename"] for a in results[0]["attachments"]]
    assert filenames == ["note.txt", "note-2.txt"]


def test_mail_dir_created_on_init(tmp_path):
    from smtpweb.storage import EmailStorage

    mail_dir = tmp_path / "does" / "not" / "exist" / "yet"
    EmailStorage(mail_dir)
    assert mail_dir.is_dir()
