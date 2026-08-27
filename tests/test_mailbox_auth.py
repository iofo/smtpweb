import json
import threading

import pytest


def test_first_login_claims_mailbox(mailbox_auth):
    result = mailbox_auth.login("bob@example.com", "hunter2")
    assert result == "bob@example.com"


def test_second_login_with_same_password_succeeds(mailbox_auth):
    mailbox_auth.login("bob@example.com", "hunter2")
    assert mailbox_auth.login("bob@example.com", "hunter2") == "bob@example.com"


def test_second_login_with_wrong_password_fails(mailbox_auth):
    mailbox_auth.login("bob@example.com", "hunter2")
    assert mailbox_auth.login("bob@example.com", "wrong-password") is None


def test_login_normalizes_username_case(mailbox_auth):
    mailbox_auth.login("Bob@Example.com", "hunter2")
    assert mailbox_auth.login("bob@example.com", "hunter2") == "bob@example.com"


def test_empty_password_rejected(mailbox_auth):
    assert mailbox_auth.login("bob@example.com", "") is None


def test_invalid_username_rejected(mailbox_auth):
    assert mailbox_auth.login("not-an-email", "hunter2") is None


def test_password_never_stored_in_plaintext(mailbox_auth, web_state_dir):
    mailbox_auth.login("bob@example.com", "hunter2-super-secret")
    creds_path = web_state_dir / "bob@example.com" / "credentials.json"
    raw = creds_path.read_text()
    assert "hunter2-super-secret" not in raw
    record = json.loads(raw)
    assert record["algorithm"] == "pbkdf2_sha256"
    assert "salt" in record and "hash" in record


def test_two_mailboxes_get_different_salts(mailbox_auth, web_state_dir):
    mailbox_auth.login("bob@example.com", "same-password")
    mailbox_auth.login("eve@example.com", "same-password")
    bob = json.loads((web_state_dir / "bob@example.com" / "credentials.json").read_text())
    eve = json.loads((web_state_dir / "eve@example.com" / "credentials.json").read_text())
    assert bob["salt"] != eve["salt"]
    assert bob["hash"] != eve["hash"]


def test_corrupted_credentials_file_fails_login_cleanly(mailbox_auth, web_state_dir):
    creds_dir = web_state_dir / "bob@example.com"
    creds_dir.mkdir(parents=True)
    (creds_dir / "credentials.json").write_text("not valid json {{{")

    # Must not raise — a corrupted file should behave like a failed login,
    # not crash the request.
    assert mailbox_auth.login("bob@example.com", "anything") is None


def test_missing_keys_in_credentials_file_fails_login_cleanly(mailbox_auth, web_state_dir):
    creds_dir = web_state_dir / "bob@example.com"
    creds_dir.mkdir(parents=True)
    (creds_dir / "credentials.json").write_text(json.dumps({"algorithm": "pbkdf2_sha256"}))

    assert mailbox_auth.login("bob@example.com", "anything") is None


def test_concurrent_first_login_claim_is_race_free(mailbox_auth):
    """Regression test: MailboxAuth.login() used to check-then-write
    credentials.json non-atomically, so two concurrent first logins for
    the same unclaimed mailbox could both report success with different
    passwords. Exactly one password must win; every other racer must be
    checked against it (and fail, since they each used a distinct
    password) rather than being told it succeeded."""
    n = 10
    results = [None] * n
    barrier = threading.Barrier(n)

    def attempt(i):
        barrier.wait()
        results[i] = mailbox_auth.login("racer@example.com", f"password-{i}")

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    successes = [i for i, r in enumerate(results) if r == "racer@example.com"]
    assert len(successes) == 1, f"expected exactly one winner, got {successes}"

    winner = successes[0]
    # The winning password must be the one actually persisted.
    assert mailbox_auth.login("racer@example.com", f"password-{winner}") == "racer@example.com"
    # Every other racer's password must NOT work afterward.
    for i in range(n):
        if i != winner:
            assert mailbox_auth.login("racer@example.com", f"password-{i}") is None
