import secrets
import threading
import time


class SessionStore:
    """In-memory login-session store: a session token maps to (mailbox,
    expiry). All FastAPI route handlers in web/app.py are plain `def`,
    which FastAPI dispatches to a real thread pool for concurrency, so
    multiple requests can touch this store at genuinely the same time.

    A plain dict's individual operations (get/set/pop) are each atomic
    under the GIL, but sweeping expired entries is a compound
    iterate-then-delete sequence that isn't atomic on its own -- a
    concurrent insert landing mid-iteration raises RuntimeError
    ("dictionary changed size during iteration"), and two sweeps (or a
    sweep and a lookup's own eviction) racing to delete the same expired
    token raise KeyError. `_lock` serializes every method here to
    eliminate both, the same way MailboxAuth's os.O_EXCL prevents its
    own claim race.

    Not shared across separate worker processes -- fine for this
    project's one-process-per-container deployment, but would need an
    external store (e.g. Redis) to stay correct under multiple workers.
    """

    def __init__(self, max_age_seconds: float):
        self._max_age_seconds = max_age_seconds
        self._sessions: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def create(self, mailbox: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sweep_expired_locked()
            self._sessions[token] = (mailbox, time.time() + self._max_age_seconds)
        return token

    def get(self, token: str | None) -> str | None:
        """Return the session's mailbox, or None if there's no session,
        it's unknown, or it's expired (evicting it as a side effect)."""
        if not token:
            return None
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None:
                return None
            mailbox, expires_at = entry
            if expires_at <= time.time():
                del self._sessions[token]
                return None
            return mailbox

    def delete(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def _sweep_expired_locked(self) -> None:
        """Must only be called with `_lock` already held."""
        now = time.time()
        expired = [token for token, (_, expires_at) in self._sessions.items() if expires_at <= now]
        for token in expired:
            del self._sessions[token]
