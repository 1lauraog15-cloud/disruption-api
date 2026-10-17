"""API key authentication. Only SHA-256 hashes of the keys are configured, never the keys."""

import hashlib
import hmac
import secrets


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def is_valid_key(key: str | None, valid_hashes: frozenset[str]) -> bool:
    """Compare in constant time against every configured hash (no early exit on a match)."""
    if not key:
        return False
    candidate = hash_key(key)
    matches = [hmac.compare_digest(candidate, known) for known in valid_hashes]
    return any(matches)


def generate_key() -> tuple[str, str]:
    """Return a new random key and its hash."""
    key = secrets.token_urlsafe(32)
    return key, hash_key(key)


if __name__ == "__main__":
    new_key, new_hash = generate_key()
    print(f"API key (give it to the client, shown once): {new_key}")
    print(f"Add to API_KEY_HASHES: {new_hash}")
