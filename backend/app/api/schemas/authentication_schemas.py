"""Wire format of the authentication endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from ...domain.user_account import UserAccount


class LoginRequest(BaseModel):
    """Credentials supplied by the sign-in form."""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    """Password rotation by the signed-in user."""

    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=256)


class CurrentUserResponse(BaseModel):
    """The account behind the current session."""

    user_id: str
    username: str
    display_name: str
    role: str
    is_administrator: bool
    quota_bytes: int
    quota_gigabytes: float
    must_change_password: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    @classmethod
    def from_account(cls, account: UserAccount) -> "CurrentUserResponse":
        return cls(
            user_id=account.user_id,
            username=account.username,
            display_name=account.display_name,
            role=account.role.value,
            is_administrator=account.is_administrator,
            quota_bytes=account.quota_bytes,
            quota_gigabytes=account.quota_gigabytes,
            must_change_password=account.must_change_password,
            created_at=account.created_at,
            last_login_at=account.last_login_at,
        )


class PasswordPolicyResponse(BaseModel):
    """Shown next to every password field in the user interface."""

    minimum_length: int
    description: str


class SimpleAcknowledgement(BaseModel):
    """Generic ``{"ok": true}`` style response."""

    ok: bool = True
    message: str = ""
