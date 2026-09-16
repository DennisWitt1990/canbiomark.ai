"""Creation and hashing of opaque session tokens."""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

_TOKEN_BYTE_LENGTH = 32


@dataclass(frozen=True)
class IssuedSessionToken:
    """A freshly minted token: the clear value goes to the browser, the hash to SQLite."""

    clear_token: str
    session_id: str


class SessionTokenFactory:
    """Generates session tokens and maps a token back to its database key."""

    def issue(self) -> IssuedSessionToken:
        clear_token = secrets.token_urlsafe(_TOKEN_BYTE_LENGTH)
        return IssuedSessionToken(
            clear_token=clear_token, session_id=self.to_session_id(clear_token)
        )

    @staticmethod
    def to_session_id(clear_token: str) -> str:
        """SHA-256 of the token; used as the ``login_sessions`` primary key."""
        return hashlib.sha256(clear_token.encode("utf-8")).hexdigest()
