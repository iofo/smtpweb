import sys
import threading

from smtpweb.web.session_store import SessionStore


def test_create_then_get_returns_mailbox():
    store = SessionStore(max_age_seconds=60)
    token = store.create("bob@example.com")
    assert store.get(token) == "bob@example.com"


def test_get_unknown_token_returns_none():
    store = SessionStore(max_age_seconds=60)
    assert store.get("nonexistent-token") is None


def test_get_none_token_returns_none():
    store = SessionStore(max_age_seconds=60)
    assert store.get(None) is None


def test_get_expired_token_returns_none_and_evicts():
    store = SessionStore(max_age_seconds=-1)  # already expired the instant it's created
    token = store.create("bob@example.com")
    assert store.get(token) is None
    # Evicted as a side effect, not just reported expired -- confirmed via
    # the internal dict since there's no other observable way to check.
    assert token not in store._sessions


def test_delete_removes_session():
    store = SessionStore(max_age_seconds=60)
    token = store.create("bob@example.com")
    store.delete(token)
    assert store.get(token) is None


def test_delete_unknown_token_is_noop():
    store = SessionStore(max_age_seconds=60)
    store.delete("nonexistent-token")  # must not raise


def test_delete_none_token_is_noop():
    store = SessionStore(max_age_seconds=60)
    store.delete(None)  # must not raise


def test_create_sweeps_expired_entries():
    store = SessionStore(max_age_seconds=-1)
    stale_token = store.create("bob@example.com")
    assert stale_token in store._sessions
    store.create("eve@example.com")  # triggers a sweep on the way in
    assert stale_token not in store._sessions


def test_concurrent_create_and_lookup_does_not_raise():
    """Regression test: sweeping expired sessions is an iterate-then-
    delete sequence that isn't atomic on its own. A concurrent insert
    landing mid-iteration used to raise RuntimeError ("dictionary
    changed size during iteration"), and two threads racing to delete
    the same expired token used to raise KeyError. Every session store
    method being called here concurrently -- create (sweeps + inserts),
    get (can itself evict), delete -- must never let either escape."""
    store = SessionStore(max_age_seconds=0.001)  # expires almost immediately
    n = 100
    errors = []
    barrier = threading.Barrier(n)

    # Force much more frequent GIL handoffs than the 5ms default, so
    # concurrent threads actually interleave mid-method instead of each
    # one completing its critical section before the next gets a turn --
    # without this, a race that's real but narrow can pass by sheer luck
    # every time on a fast machine.
    original_interval = sys.getswitchinterval()
    sys.setswitchinterval(0.00001)
    try:

        def hammer(i):
            barrier.wait()
            try:
                for _ in range(100):
                    token = store.create(f"racer-{i}@example.com")
                    store.get(token)
                    store.delete(token)
            except Exception as exc:  # noqa: BLE001 -- capturing any race, not a specific type
                errors.append(exc)

        threads = [threading.Thread(target=hammer, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(original_interval)

    assert errors == [], f"session store raised under concurrent access: {errors!r}"
