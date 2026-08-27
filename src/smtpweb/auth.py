import hmac
import json
import secrets
from pathlib import Path

from aiosmtpd.smtp import AuthResult, LoginPassword


class Authenticator:
    """Validates AUTH LOGIN/PLAIN credentials against a single configured
    username/password using constant-time comparison."""

    def __init__(self, username: str, password: str):
        self._username = username.encode("utf-8")
        self._password = password.encode("utf-8")

    def __call__(self, server, session, envelope, mechanism, auth_data):
        if mechanism not in ("LOGIN", "PLAIN") or not isinstance(auth_data, LoginPassword):
            return AuthResult(success=False, handled=False)
        login_ok = hmac.compare_digest(auth_data.login, self._username)
        password_ok = hmac.compare_digest(auth_data.password, self._password)
        if login_ok and password_ok:
            return AuthResult(success=True)
        return AuthResult(success=False, handled=False)


def resolve_credentials(
    creds_path: Path, env_username: str | None, env_password: str | None
) -> tuple[str, str, bool]:
    """Return (username, password, generated). If both env vars are set,
    use them. If only one is set, that's a misconfiguration. Otherwise
    reuse or generate random credentials persisted at creds_path."""
    if env_username and env_password:
        return env_username, env_password, False
    if env_username or env_password:
        raise RuntimeError(
            "Set both SMTPWEB_SMTP_USERNAME and SMTPWEB_SMTP_PASSWORD, or neither "
            "(to auto-generate credentials)."
        )

    if creds_path.exists():
        data = json.loads(creds_path.read_text())
        return data["username"], data["password"], True

    username = "smtpweb"
    password = secrets.token_urlsafe(24)
    creds_path.parent.mkdir(parents=True, exist_ok=True)
    creds_path.write_text(json.dumps({"username": username, "password": password}, indent=2))
    creds_path.chmod(0o600)
    return username, password, True
