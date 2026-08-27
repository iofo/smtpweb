import pytest

from .conftest import MINIMAL_PDF_BYTES, make_envelope


def test_save_message_creates_mailbox_and_files(storage, mail_dir):
    results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
    assert len(results) == 1
    meta = results[0]
    assert meta["mailbox"] == "bob@example.com"

    email_dir = mail_dir / "bob@example.com" / "emails" / meta["id"]
    assert (email_dir / "raw.eml").exists()
    assert (email_dir / "metadata.json").exists()
    assert (email_dir / "body.txt").read_text().strip() == "Hello, this is the body."


def test_written_files_are_owner_only(storage, mail_dir):
    results = storage.save_message(
        make_envelope(
            rcpt_tos=("bob@example.com",),
            html="<p>hi</p>",
            attachments=[("note.txt", "text/plain", b"x"), ("scan.pdf", "application/pdf", MINIMAL_PDF_BYTES)],
        )
    )
    meta = results[0]
    email_dir = mail_dir / "bob@example.com" / "emails" / meta["id"]

    checked = [
        email_dir / "raw.eml",
        email_dir / "metadata.json",
        email_dir / "body.txt",
        email_dir / "body.html",
        email_dir / "attachments" / "note.txt",
        email_dir / "attachments" / "scan.pdf",
        email_dir / "attachments" / "thumbnails" / "scan.pdf.png",
    ]
    for path in checked:
        mode = path.stat().st_mode & 0o777
        assert mode == 0o600, f"{path} has mode {oct(mode)}, expected 0o600"


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
    assert att["has_thumbnail"] is False

    path = storage.get_attachment_path(meta["mailbox"], meta["id"], "note.txt")
    assert path.read_bytes() == b"attachment bytes"


def test_pdf_attachment_gets_thumbnail(storage):
    results = storage.save_message(
        make_envelope(attachments=[("scan.pdf", "application/pdf", MINIMAL_PDF_BYTES)])
    )
    meta = results[0]
    att = meta["attachments"][0]
    assert att["has_thumbnail"] is True

    thumb_path = storage.get_attachment_thumbnail_path(meta["mailbox"], meta["id"], "scan.pdf")
    assert thumb_path.exists()
    assert thumb_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_corrupted_pdf_attachment_has_no_thumbnail(storage):
    results = storage.save_message(
        make_envelope(attachments=[("scan.pdf", "application/pdf", b"not a real pdf")])
    )
    meta = results[0]
    att = meta["attachments"][0]
    assert att["has_thumbnail"] is False

    thumb_path = storage.get_attachment_thumbnail_path(meta["mailbox"], meta["id"], "scan.pdf")
    assert not thumb_path.exists()


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


def test_list_emails_cache_returns_same_object_when_unchanged(storage):
    """The mtime-based cache should skip re-reading from disk when
    nothing has changed — verified by identity (`is`), not just
    equality, since a fresh glob+parse would produce an equal-but-new
    list object each time."""
    storage.save_message(make_envelope(subject="first"))
    first_call = storage.list_emails("bob@example.com")
    second_call = storage.list_emails("bob@example.com")
    assert first_call is second_call


def test_list_emails_cache_invalidates_on_new_message(storage):
    """Regression test for the mtime-based cache: a new message must
    show up on the very next list_emails() call, from either the same
    EmailStorage instance (this test) or a different one pointed at
    the same directory (the smtp/web process split in production)."""
    storage.save_message(make_envelope(subject="first"))
    assert len(storage.list_emails("bob@example.com")) == 1

    storage.save_message(make_envelope(subject="second"))
    emails = storage.list_emails("bob@example.com")
    assert len(emails) == 2
    assert {e["subject"] for e in emails} == {"first", "second"}


def test_list_emails_cache_invalidates_across_storage_instances(mail_dir):
    """The real-world case: the smtp process and the web process each
    have their own EmailStorage instance over the same directory."""
    from smtpweb.common.storage import EmailStorage

    writer = EmailStorage(mail_dir)
    reader = EmailStorage(mail_dir)

    writer.save_message(make_envelope(subject="from smtp process"))
    assert len(reader.list_emails("bob@example.com")) == 1

    writer.save_message(make_envelope(subject="a second one"))
    assert len(reader.list_emails("bob@example.com")) == 2


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
    from smtpweb.common.storage import EmailStorage

    mail_dir = tmp_path / "does" / "not" / "exist" / "yet"
    EmailStorage(mail_dir)
    assert mail_dir.is_dir()


def test_delete_email_removes_everything(storage, mail_dir):
    results = storage.save_message(
        make_envelope(
            rcpt_tos=("bob@example.com",),
            attachments=[("scan.pdf", "application/pdf", MINIMAL_PDF_BYTES)],
        )
    )
    meta = results[0]
    email_dir = mail_dir / "bob@example.com" / "emails" / meta["id"]
    assert email_dir.exists()

    storage.delete_email("bob@example.com", meta["id"])

    assert not email_dir.exists()
    assert storage.list_emails("bob@example.com") == []


def test_delete_email_missing_id_raises(storage):
    storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
    with pytest.raises(FileNotFoundError):
        storage.delete_email("bob@example.com", "00000000-0000-0000-0000-000000000000")


def test_delete_email_only_affects_target_email(storage):
    results = storage.save_message(make_envelope(subject="keep me"))
    keep_id = results[0]["id"]
    results = storage.save_message(make_envelope(subject="delete me"))
    delete_id = results[0]["id"]

    storage.delete_email("bob@example.com", delete_id)

    remaining = storage.list_emails("bob@example.com")
    assert len(remaining) == 1
    assert remaining[0]["id"] == keep_id
    with pytest.raises(FileNotFoundError):
        storage.get_email("bob@example.com", delete_id)


def test_delete_email_does_not_affect_other_mailboxes(storage):
    results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com", "eve@example.com")))
    shared_id = results[0]["id"]

    storage.delete_email("bob@example.com", shared_id)

    assert storage.list_emails("bob@example.com") == []
    assert len(storage.list_emails("eve@example.com")) == 1


def test_delete_email_invalidates_list_cache(storage):
    """Regression test for the mtime-based list_emails() cache: a
    deletion must be visible on the very next call, the same way a new
    message is (see test_list_emails_cache_invalidates_on_new_message)."""
    storage.save_message(make_envelope(subject="first"))
    results = storage.save_message(make_envelope(subject="second"))
    assert len(storage.list_emails("bob@example.com")) == 2

    storage.delete_email("bob@example.com", results[0]["id"])

    remaining = storage.list_emails("bob@example.com")
    assert len(remaining) == 1
    assert remaining[0]["subject"] == "first"
