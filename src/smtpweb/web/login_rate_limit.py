import threading
import time


class LoginRateLimiter:
    """Caps failed /api/login attempts per mailbox to slow down password
    guessing. Mirrors SessionStore's shape (a dict behind one global
    Lock -- see its docstring for why a single lock is fine here too:
    every operation is a cheap dict read/write, not I/O) and the same
    limitation: in-memory and per-process, so it resets on restart and
    doesn't share state across multiple web replicas. Fine for this
    project's single-process-per-container deployment.

    Tracks failures in a fixed window per mailbox: `max_attempts`
    failures within `window_seconds` blocks further attempts for that
    mailbox until the window rolls over. A successful login resets the
    mailbox's count immediately, so a legitimate user who mistypes a
    couple of times isn't penalized once they get it right.
    """

    def __init__(self, max_attempts: int, window_seconds: float):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        # mailbox -> (failure_count, window_started_at)
        self._failures: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def is_limited(self, mailbox: str) -> bool:
        with self._lock:
            entry = self._failures.get(mailbox)
            if entry is None:
                return False
            count, window_started_at = entry
            if time.time() - window_started_at >= self._window_seconds:
                del self._failures[mailbox]
                return False
            return count >= self._max_attempts

    def record_failure(self, mailbox: str) -> None:
        with self._lock:
            count, window_started_at = self._failures.get(mailbox, (0, time.time()))
            if time.time() - window_started_at >= self._window_seconds:
                count, window_started_at = 0, time.time()
            self._failures[mailbox] = (count + 1, window_started_at)

    def reset(self, mailbox: str) -> None:
        with self._lock:
            self._failures.pop(mailbox, None)
