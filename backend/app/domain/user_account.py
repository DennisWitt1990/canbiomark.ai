"""The user account aggregate."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    """Role of an account; drives every authorization decision."""

    ADMINISTRATOR = "administrator"
    RESEARCHER = "researcher"

    @classmethod
    def parse(cls, raw_value: str) -> "UserRole":
        normalized = (raw_value or "").strip().lower()
        for role in cls:
            if role.value == normalized:
                return role
        from .errors import ValidationError

        raise ValidationError(
            f"Unknown user role {raw_value!r}. Valid values: "
            + ", ".join(role.value for role in cls)
        )

    @property
    def is_administrator(self) -> bool:
        return self is UserRole.ADMINISTRATOR


@dataclass(frozen=True)
class UserAccount:
    """An account that can sign in and own a workspace.

    The password is never part of this object; only its derived hash lives in
    the repository layer.
    """

    user_id: str
    username: str
    display_name: str
    role: UserRole
    quota_bytes: int
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    @property
    def is_administrator(self) -> bool:
        return self.role.is_administrator

    @property
    def quota_gigabytes(self) -> float:
        return round(self.quota_bytes / (1024 * 1024 * 1024), 2)

    def with_login_timestamp(self, moment: Optional[datetime] = None) -> "UserAccount":
        return replace(self, last_login_at=moment or datetime.now(timezone.utc))

    def require_active(self) -> None:
        from .errors import AuthorizationError

        if not self.is_active:
            raise AuthorizationError("This account has been disabled.")

    def require_administrator(self) -> None:
        from .errors import AuthorizationError

        if not self.is_administrator:
            raise AuthorizationError("Administrator privileges are required.")

    @staticmethod
    def normalize_username(raw_username: str) -> str:
        """Usernames are case-insensitive and stored lower case."""
        normalized = (raw_username or "").strip().lower()
        if not normalized:
            raise ValueError("Username must not be empty.")
        return normalized
