"""A signed-in browser session."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class LoginSession:
    """One issued session cookie.

    Only the *hash* of the session token is persisted, so a database leak does
    not hand out usable cookies.
    """

    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: Optional[datetime]
    revoked_at: Optional[datetime]
    client_description: str = ""

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        reference = now or datetime.now(timezone.utc)
        return self.expires_at <= reference

    def is_usable(self, now: Optional[datetime] = None) -> bool:
        return not self.is_revoked and not self.is_expired(now)
