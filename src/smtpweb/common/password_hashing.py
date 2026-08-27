import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 310_000


def hash_password(password: str) -> dict:
    """Return a PBKDF2-HMAC-SHA256 record for `password` with a fresh
    random salt. Never store the password itself — only this record."""
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return {
        "algorithm": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": salt.hex(),
        "hash": derived.hex(),
    }


def verify_password(password: str, record: dict) -> bool:
    """Constant-time check of `password` against a record from hash_password."""
    salt = bytes.fromhex(record["salt"])
    expected = bytes.fromhex(record["hash"])
    iterations = record.get("iterations", PBKDF2_ITERATIONS)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)
