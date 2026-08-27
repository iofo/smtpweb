from pathlib import Path

from smtpweb.common.config import Settings


def test_defaults_when_unset(monkeypatch):
    for var in [
        "SMTPWEB_SMTP_HOST",
        "SMTPWEB_SMTP_PORT",
        "SMTPWEB_SMTP_USERNAME",
        "SMTPWEB_SMTP_PASSWORD",
        "SMTPWEB_WEB_HOST",
        "SMTPWEB_WEB_PORT",
        "SMTPWEB_MAIL_DIR",
        "SMTPWEB_SMTP_STATE_DIR",
        "SMTPWEB_WEB_STATE_DIR",
    ]:
        monkeypatch.delenv(var, raising=False)

    settings = Settings()
    assert settings.smtp_host == "0.0.0.0"
    assert settings.smtp_port == 1025
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.web_host == "0.0.0.0"
    assert settings.web_port == 8080
    assert settings.mail_dir == Path("./data/mail")
    assert settings.smtp_state_dir == Path("./data/smtp")
    assert settings.web_state_dir == Path("./data/web")


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
