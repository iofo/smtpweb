from .conftest import MINIMAL_PDF_BYTES, make_envelope


def login(client, username, password):
    return client.post("/api/login", json={"username": username, "password": password})


class TestLogin:
    def test_unauthenticated_request_rejected(self, app_client):
        response = app_client.get("/api/me")
        assert response.status_code == 401

    def test_first_login_claims_mailbox(self, app_client):
        response = login(app_client, "bob@example.com", "bobs-password")
        assert response.status_code == 200
        assert response.json() == {"username": "bob@example.com"}
        assert "smtpweb_session" in response.cookies

    def test_authenticated_request_after_login(self, app_client):
        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get("/api/me")
        assert response.status_code == 200
        assert response.json() == {"username": "bob@example.com"}

    def test_second_login_wrong_password_rejected(self, app_client):
        login(app_client, "bob@example.com", "bobs-password")
        app_client.cookies.clear()
        response = login(app_client, "bob@example.com", "wrong-password")
        assert response.status_code == 401

    def test_second_login_correct_password_succeeds(self, app_client):
        login(app_client, "bob@example.com", "bobs-password")
        app_client.cookies.clear()
        response = login(app_client, "bob@example.com", "bobs-password")
        assert response.status_code == 200

    def test_username_is_case_insensitive_for_login(self, app_client):
        login(app_client, "Bob@Example.com", "bobs-password")
        app_client.cookies.clear()
        response = login(app_client, "bob@example.com", "bobs-password")
        assert response.status_code == 200

    def test_logout_clears_session(self, app_client):
        login(app_client, "bob@example.com", "bobs-password")
        assert app_client.get("/api/me").status_code == 200
        app_client.post("/api/logout")
        assert app_client.get("/api/me").status_code == 401


class TestMailboxIsolation:
    def test_inbox_only_shows_own_mail(self, app_client, storage):
        storage.save_message(make_envelope(rcpt_tos=("bob@example.com",), subject="For Bob"))
        storage.save_message(make_envelope(rcpt_tos=("eve@example.com",), subject="For Eve"))

        login(app_client, "bob@example.com", "bobs-password")
        subjects = {e["subject"] for e in app_client.get("/api/emails").json()}
        assert subjects == {"For Bob"}

    def test_cannot_fetch_another_mailboxes_email_by_id(self, app_client, storage):
        results = storage.save_message(
            make_envelope(rcpt_tos=("bob@example.com",), subject="Bob only")
        )
        bob_email_id = results[0]["id"]

        login(app_client, "eve@example.com", "eves-password")
        response = app_client.get(f"/api/emails/{bob_email_id}")
        assert response.status_code == 404

    def test_shared_message_visible_to_both_recipients(self, app_client, storage):
        results = storage.save_message(
            make_envelope(rcpt_tos=("bob@example.com", "eve@example.com"), subject="Both")
        )
        shared_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        assert app_client.get(f"/api/emails/{shared_id}").status_code == 200

        app_client.cookies.clear()
        login(app_client, "eve@example.com", "eves-password")
        assert app_client.get(f"/api/emails/{shared_id}").status_code == 200


class TestEmailDetail:
    def test_get_email_detail_includes_body(self, app_client, storage):
        results = storage.save_message(
            make_envelope(rcpt_tos=("bob@example.com",), text="plain body", html="<p>html body</p>")
        )
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        detail = app_client.get(f"/api/emails/{email_id}").json()
        assert "plain body" in detail["text_body"]
        assert "html body" in detail["html_body"]

    def test_download_raw_eml(self, app_client, storage):
        results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/raw")
        assert response.status_code == 200
        assert response.headers["content-type"] == "message/rfc822"

    def test_download_attachment(self, app_client, storage):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("note.txt", "text/plain", b"attachment contents")],
            )
        )
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/note.txt")
        assert response.status_code == 200
        assert response.content == b"attachment contents"

    def test_missing_attachment_404s(self, app_client, storage):
        results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/does-not-exist.txt")
        assert response.status_code == 404


class TestAttachmentDisposition:
    """PDF/image/text attachments should preview inline in the browser;
    everything else (and especially anything that could carry a script,
    like HTML or SVG) must still force a download — see the
    INLINE_SAFE_MEDIA_TYPES comment in web/app.py."""

    def _upload_and_fetch(self, app_client, storage, filename, content=b"data"):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[(filename, "application/octet-stream", content)],
            )
        )
        email_id = results[0]["id"]
        login(app_client, "bob@example.com", "bobs-password")
        return app_client.get(f"/api/emails/{email_id}/attachments/{filename}")

    def test_pdf_is_inline(self, app_client, storage):
        response = self._upload_and_fetch(app_client, storage, "scan.pdf", b"%PDF-1.4")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert "inline" in response.headers["content-disposition"]

    def test_png_is_inline(self, app_client, storage):
        response = self._upload_and_fetch(app_client, storage, "photo.png")
        assert "inline" in response.headers["content-disposition"]

    def test_plain_text_is_inline(self, app_client, storage):
        response = self._upload_and_fetch(app_client, storage, "note.txt")
        assert "inline" in response.headers["content-disposition"]

    def test_html_attachment_forces_download_not_inline(self, app_client, storage):
        """The critical case: an HTML (or SVG) attachment must never be
        set to render inline, since it's served from this app's own
        origin and could carry a script with access to the session."""
        response = self._upload_and_fetch(app_client, storage, "evil.html", b"<script>1</script>")
        assert "attachment" in response.headers["content-disposition"]
        assert "inline" not in response.headers["content-disposition"]

    def test_svg_attachment_forces_download_not_inline(self, app_client, storage):
        response = self._upload_and_fetch(app_client, storage, "evil.svg", b"<svg onload=alert(1)>")
        assert "attachment" in response.headers["content-disposition"]

    def test_unknown_extension_defaults_to_attachment(self, app_client, storage):
        response = self._upload_and_fetch(app_client, storage, "mystery.bin")
        assert "attachment" in response.headers["content-disposition"]

    def test_disposition_ignores_claimed_content_type_lie(self, app_client, storage):
        """A sender claiming an .html file is "application/pdf" in the
        MIME headers must not get it treated as inline — disposition is
        decided from the filename extension server-side, not trusted
        sender-supplied metadata."""
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("evil.html", "application/pdf", b"<script>1</script>")],
            )
        )
        email_id = results[0]["id"]
        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/evil.html")
        assert "attachment" in response.headers["content-disposition"]

    def test_nosniff_header_present(self, app_client, storage):
        response = self._upload_and_fetch(app_client, storage, "scan.pdf")
        assert response.headers["x-content-type-options"] == "nosniff"


class TestPdfThumbnail:
    def test_pdf_attachment_has_thumbnail_in_metadata(self, app_client, storage):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("scan.pdf", "application/pdf", MINIMAL_PDF_BYTES)],
            )
        )
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        detail = app_client.get(f"/api/emails/{email_id}").json()
        assert detail["attachments"][0]["has_thumbnail"] is True

    def test_thumbnail_endpoint_returns_png(self, app_client, storage):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("scan.pdf", "application/pdf", MINIMAL_PDF_BYTES)],
            )
        )
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/scan.pdf/thumbnail")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert "inline" in response.headers["content-disposition"]

    def test_non_pdf_attachment_has_no_thumbnail(self, app_client, storage):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("note.txt", "text/plain", b"hello")],
            )
        )
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/note.txt/thumbnail")
        assert response.status_code == 404

    def test_corrupted_pdf_thumbnail_404s(self, app_client, storage):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("scan.pdf", "application/pdf", b"not a real pdf")],
            )
        )
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/scan.pdf/thumbnail")
        assert response.status_code == 404

    def test_thumbnail_requires_session(self, app_client):
        response = app_client.get("/api/emails/some-id/attachments/f.pdf/thumbnail")
        assert response.status_code == 401

    def test_cannot_fetch_another_mailboxes_thumbnail(self, app_client, storage):
        results = storage.save_message(
            make_envelope(
                rcpt_tos=("bob@example.com",),
                attachments=[("scan.pdf", "application/pdf", MINIMAL_PDF_BYTES)],
            )
        )
        email_id = results[0]["id"]

        login(app_client, "eve@example.com", "eves-password")
        response = app_client.get(f"/api/emails/{email_id}/attachments/scan.pdf/thumbnail")
        assert response.status_code == 404


class TestDeleteEmail:
    def test_delete_removes_email(self, app_client, storage):
        results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
        email_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.delete(f"/api/emails/{email_id}")
        assert response.status_code == 204

        assert app_client.get(f"/api/emails/{email_id}").status_code == 404
        assert app_client.get("/api/emails").json() == []

    def test_delete_nonexistent_email_404s(self, app_client):
        login(app_client, "bob@example.com", "bobs-password")
        response = app_client.delete("/api/emails/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404

    def test_delete_requires_session(self, app_client):
        assert app_client.delete("/api/emails/some-id").status_code == 401

    def test_cannot_delete_another_mailboxes_email(self, app_client, storage):
        """The critical case: a mailbox must not be able to delete an
        email it can't even see, by guessing another mailbox's id."""
        results = storage.save_message(make_envelope(rcpt_tos=("bob@example.com",)))
        email_id = results[0]["id"]

        login(app_client, "eve@example.com", "eves-password")
        response = app_client.delete(f"/api/emails/{email_id}")
        assert response.status_code == 404

        # Bob's copy must be untouched.
        app_client.cookies.clear()
        login(app_client, "bob@example.com", "bobs-password")
        assert app_client.get(f"/api/emails/{email_id}").status_code == 200

    def test_deleting_shared_message_only_removes_callers_copy(self, app_client, storage):
        results = storage.save_message(
            make_envelope(rcpt_tos=("bob@example.com", "eve@example.com"))
        )
        shared_id = results[0]["id"]

        login(app_client, "bob@example.com", "bobs-password")
        assert app_client.delete(f"/api/emails/{shared_id}").status_code == 204

        app_client.cookies.clear()
        login(app_client, "eve@example.com", "eves-password")
        assert app_client.get(f"/api/emails/{shared_id}").status_code == 200


class TestUnauthenticatedAccessBlocked:
    def test_emails_list_requires_session(self, app_client):
        assert app_client.get("/api/emails").status_code == 401

    def test_email_detail_requires_session(self, app_client):
        assert app_client.get("/api/emails/some-id").status_code == 401

    def test_attachment_requires_session(self, app_client):
        assert app_client.get("/api/emails/some-id/attachments/f.txt").status_code == 401

    def test_openapi_docs_are_disabled(self, app_client):
        """Regression test: FastAPI's auto-generated /docs, /redoc, and
        /openapi.json are the one thing that would otherwise be reachable
        with no session at all, handing an anonymous visitor the full API
        surface — see docs_url=None in create_app()."""
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert app_client.get(path).status_code == 404, path
