"""Salted password hashing based on PBKDF2-HMAC-SHA256.

PBKDF2 ships with the Python standard library, so the container needs no extra
dependency.  The per-hash iteration count is stored alongside the hash, which
lets the cost factor be raised later without invalidating existing passwords.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

_SALT_BYTE_LENGTH = 16
_DERIVED_KEY_LENGTH = 32


@dataclass(frozen=True)
class PasswordHash:
    """Everything needed to verify a password later on."""

    hash_hex: str
    salt_hex: str
    iterations: int


class PasswordHasher:
    """Derives and verifies password hashes."""

    def __init__(self, iterations: int = 240_000) -> None:
        if iterations < 10_000:
            raise ValueError("Refusing to use fewer than 10000 PBKDF2 iterations.")
        self._iterations = iterations

    @property
    def iterations(self) -> int:
        return self._iterations

    def hash_password(self, plain_password: str) -> PasswordHash:
        salt_bytes = secrets.token_bytes(_SALT_BYTE_LENGTH)
        derived_key = self._derive_key(plain_password, salt_bytes, self._iterations)
        return PasswordHash(
            hash_hex=derived_key.hex(),
            salt_hex=salt_bytes.hex(),
            iterations=self._iterations,
        )

    def verify_password(self, plain_password: str, stored_hash: PasswordHash) -> bool:
        """Constant-time comparison against a stored hash."""
        try:
            salt_bytes = bytes.fromhex(stored_hash.salt_hex)
            expected_bytes = bytes.fromhex(stored_hash.hash_hex)
        except ValueError:
            return False

        candidate_bytes = self._derive_key(
            plain_password, salt_bytes, stored_hash.iterations
        )
        return hmac.compare_digest(candidate_bytes, expected_bytes)

    def needs_rehash(self, stored_hash: PasswordHash) -> bool:
        """True when the stored hash uses a weaker cost factor than configured."""
        return stored_hash.iterations < self._iterations

    @staticmethod
    def _derive_key(plain_password: str, salt_bytes: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt_bytes,
            iterations,
            dklen=_DERIVED_KEY_LENGTH,
        )
