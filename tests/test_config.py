from pathlib import Path

import pytest

from smtpweb.common.config import Settings


def test_defaults_when_unset(monkeypatch):
    for var in [
        "SMTPWEB_SMTP_HOST",
        "SMTPWEB_SMTP_PORT",
        "SMTPWEB_SMTP_USERNAME",
        "SMTPWEB_SMTP_PASSWORD",
        "SMTPWEB_WEB_HOST",
        "SMTPWEB_WEB_PORT",
        "SMTPWEB_WEB_TLS",
        "SMTPWEB_MAIL_DIR",
        "SMTPWEB_SMTP_STATE_DIR",
        "SMTPWEB_WEB_STATE_DIR",
        "SMTPWEB_GIT_SHA",
    ]:
        monkeypatch.delenv(var, raising=False)

    settings = Settings()
    assert settings.smtp_host == "0.0.0.0"
    assert settings.smtp_port == 1025
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.web_host == "0.0.0.0"
    assert settings.web_port == 8080
    assert settings.web_tls_enabled is True
    assert settings.mail_dir == Path("./data/mail")
    assert settings.smtp_state_dir == Path("./data/smtp")
    assert settings.web_state_dir == Path("./data/web")
    assert settings.git_sha == "dev"


def test_git_sha_reads_from_environment(monkeypatch):
    monkeypatch.setenv("SMTPWEB_GIT_SHA", "abc1234")
    assert Settings().git_sha == "abc1234"


@pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "on"])
def test_web_tls_truthy_values(monkeypatch, value):
    monkeypatch.setenv("SMTPWEB_WEB_TLS", value)
    assert Settings().web_tls_enabled is True


@pytest.mark.parametrize("value", ["false", "False", "0", "no", "off", "garbage", ""])
def test_web_tls_falsy_values(monkeypatch, value):
    monkeypatch.setenv("SMTPWEB_WEB_TLS", value)
    assert Settings().web_tls_enabled is False


def test_reads_environment_set_after_module_import(monkeypatch):
    """Regression test: Settings' dataclass fields used to read
    os.environ via plain `= os.environ.get(...)` defaults, which Python
    evaluates once at class definition (module import) time, not per
    Settings() call — so env vars set after import (as any test using
    monkeypatch does) were silently ignored. Fields now use
    default_factory so each Settings() call re-reads the environment."""
    monkeypatch.setenv("SMTPWEB_SMTP_PORT", "9999")
    monkeypatch.setenv("SMTPWEB_WEB_PORT", "8888")
    monkeypatch.setenv("SMTPWEB_SMTP_USERNAME", "custom-user")
    monkeypatch.setenv("SMTPWEB_MAIL_DIR", "/custom/mail")

    settings = Settings()
    assert settings.smtp_port == 9999
    assert settings.web_port == 8888
    assert settings.smtp_username == "custom-user"
    assert settings.mail_dir == Path("/custom/mail")


def test_two_instances_can_see_different_environments(monkeypatch):
    monkeypatch.setenv("SMTPWEB_SMTP_PORT", "1111")
    first = Settings()
    monkeypatch.setenv("SMTPWEB_SMTP_PORT", "2222")
    second = Settings()
    assert first.smtp_port == 1111
    assert second.smtp_port == 2222
