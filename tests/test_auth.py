import json

import pytest
from aiosmtpd.smtp import LoginPassword

from smtpweb.auth import Authenticator, resolve_credentials

ENV_NAMES = ("SMTPWEB_SMTP_USERNAME", "SMTPWEB_SMTP_PASSWORD")


class TestAuthenticator:
    def test_correct_credentials_succeed(self):
        authenticator = Authenticator("alice", "s3cret")
        result = authenticator(
            None, None, None, "PLAIN", LoginPassword(b"alice", b"s3cret")
        )
        assert result.success is True

    def test_wrong_password_fails(self):
        authenticator = Authenticator("alice", "s3cret")
        result = authenticator(
            None, None, None, "PLAIN", LoginPassword(b"alice", b"wrong")
        )
        assert result.success is False

    def test_wrong_username_fails(self):
        authenticator = Authenticator("alice", "s3cret")
        result = authenticator(
            None, None, None, "LOGIN", LoginPassword(b"mallory", b"s3cret")
        )
        assert result.success is False

    def test_unsupported_mechanism_rejected(self):
        authenticator = Authenticator("alice", "s3cret")
        result = authenticator(
            None, None, None, "CRAM-MD5", LoginPassword(b"alice", b"s3cret")
        )
        assert result.success is False

    def test_non_login_password_auth_data_rejected(self):
        authenticator = Authenticator("alice", "s3cret")
        result = authenticator(None, None, None, "PLAIN", "not-a-login-password")
        assert result.success is False


class TestResolveCredentials:
    def test_both_env_vars_set_used_directly(self, tmp_path):
        username, password, generated = resolve_credentials(
            tmp_path / "creds.json", "envuser", "envpass", ENV_NAMES, "default"
        )
        assert (username, password, generated) == ("envuser", "envpass", False)
        assert not (tmp_path / "creds.json").exists()

    def test_only_username_set_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            resolve_credentials(tmp_path / "creds.json", "envuser", None, ENV_NAMES, "default")

    def test_only_password_set_raises(self, tmp_path):
        with pytest.raises(RuntimeError):
            resolve_credentials(tmp_path / "creds.json", None, "envpass", ENV_NAMES, "default")

    def test_neither_set_generates_and_persists(self, tmp_path):
        creds_path = tmp_path / "creds.json"
        username, password, generated = resolve_credentials(
            creds_path, None, None, ENV_NAMES, "smtpweb"
        )
        assert generated is True
        assert username == "smtpweb"
        assert len(password) > 0
        saved = json.loads(creds_path.read_text())
        assert saved == {"username": username, "password": password}

    def test_neither_set_reuses_existing_file(self, tmp_path):
        creds_path = tmp_path / "creds.json"
        creds_path.parent.mkdir(parents=True, exist_ok=True)
        creds_path.write_text(json.dumps({"username": "existing", "password": "existing-pw"}))

        username, password, generated = resolve_credentials(
            creds_path, None, None, ENV_NAMES, "smtpweb"
        )
        assert (username, password, generated) == ("existing", "existing-pw", True)

    def test_generated_credentials_are_random(self, tmp_path):
        _, password_a, _ = resolve_credentials(
            tmp_path / "a.json", None, None, ENV_NAMES, "smtpweb"
        )
        _, password_b, _ = resolve_credentials(
            tmp_path / "b.json", None, None, ENV_NAMES, "smtpweb"
        )
        assert password_a != password_b
