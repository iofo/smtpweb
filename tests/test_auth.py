import json

import pytest
from aiosmtpd.smtp import LoginPassword

from smtpweb.common.password_hashing import hash_password
from smtpweb.smtp.auth import Authenticator, resolve_credentials

ENV_NAMES = ("SMTPWEB_SMTP_USERNAME", "SMTPWEB_SMTP_PASSWORD")


class TestAuthenticator:
    def _authenticator(self, username="alice", password="s3cret"):
        return Authenticator(username, hash_password(password))

    def test_correct_credentials_succeed(self):
        authenticator = self._authenticator()
        result = authenticator(None, None, None, "PLAIN", LoginPassword(b"alice", b"s3cret"))
        assert result.success is True

    def test_wrong_password_fails(self):
        authenticator = self._authenticator()
        result = authenticator(None, None, None, "PLAIN", LoginPassword(b"alice", b"wrong"))
        assert result.success is False

    def test_wrong_username_fails(self):
        authenticator = self._authenticator()
        result = authenticator(None, None, None, "LOGIN", LoginPassword(b"mallory", b"s3cret"))
        assert result.success is False

    def test_unsupported_mechanism_rejected(self):
        authenticator = self._authenticator()
        result = authenticator(None, None, None, "CRAM-MD5", LoginPassword(b"alice", b"s3cret"))
        assert result.success is False

    def test_non_login_password_auth_data_rejected(self):
        authenticator = self._authenticator()
        result = authenticator(None, None, None, "PLAIN", "not-a-login-password")
        assert result.success is False

    def test_non_utf8_password_bytes_rejected_not_raised(self):
        authenticator = self._authenticator()
        result = authenticator(None, None, None, "PLAIN", LoginPassword(b"alice", b"\xff\xfe\xfd"))
        assert result.success is False

    def test_corrupted_password_record_rejected_not_raised(self):
        authenticator = Authenticator("alice", {"algorithm": "pbkdf2_sha256"})
        result = authenticator(None, None, None, "PLAIN", LoginPassword(b"alice", b"s3cret"))
        assert result.success is False


class TestResolveCredentials:
    def test_both_env_vars_set_used_directly(self, tmp_path):
        username, record, generated, new_password = resolve_credentials(
            tmp_path / "creds.json", "envuser", "envpass", ENV_NAMES, "default"
        )
        assert username == "envuser"
        assert generated is False
        assert new_password is None
        assert not (tmp_path / "creds.json").exists()
        # The record must verify the real password and be a hash, not it.
        from smtpweb.common.password_hashing import verify_password

        assert verify_password("envpass", record)
        assert "envpass" not in json.dumps(record)

    def test_only_username_set_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            resolve_credentials(tmp_path / "creds.json", "envuser", None, ENV_NAMES, "default")

    def test_only_password_set_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            resolve_credentials(tmp_path / "creds.json", None, "envpass", ENV_NAMES, "default")

    def test_neither_set_generates_and_persists_hash_only(self, tmp_path):
        creds_path = tmp_path / "creds.json"
        username, record, generated, new_password = resolve_credentials(
            creds_path, None, None, ENV_NAMES, "smtpweb"
        )
        assert generated is True
        assert username == "smtpweb"
        assert new_password is not None and len(new_password) > 0

        saved = json.loads(creds_path.read_text())
        assert saved["username"] == "smtpweb"
        assert "salt" in saved and "hash" in saved
        # The plaintext must never be written to disk.
        assert new_password not in creds_path.read_text()

    def test_neither_set_reuses_existing_file_without_replaintext(self, tmp_path):
        creds_path = tmp_path / "creds.json"
        creds_path.parent.mkdir(parents=True, exist_ok=True)
        existing_record = {"username": "existing", **hash_password("existing-pw")}
        creds_path.write_text(json.dumps(existing_record))

        username, record, generated, new_password = resolve_credentials(
            creds_path, None, None, ENV_NAMES, "smtpweb"
        )
        assert username == "existing"
        assert generated is True
        # Loading a pre-existing file never yields the plaintext back.
        assert new_password is None

        from smtpweb.common.password_hashing import verify_password

        assert verify_password("existing-pw", record)

    def test_generated_credentials_are_random(self, tmp_path):
        _, _, _, password_a = resolve_credentials(
            tmp_path / "a.json", None, None, ENV_NAMES, "smtpweb"
        )
        _, _, _, password_b = resolve_credentials(
            tmp_path / "b.json", None, None, ENV_NAMES, "smtpweb"
        )
        assert password_a != password_b
