"""Wire format of the administrator endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from ...database.repositories.audit_repository import AuditEvent
from ...domain.login_session import LoginSession
from ...domain.user_account import UserAccount, UserRole
from ...services.user_administration_service import AccountUsage

_BYTES_PER_GIGABYTE = 1024 * 1024 * 1024


class ManagedUserResponse(BaseModel):
    """One row of the user administration table."""

    user_id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    must_change_password: bool
    quota_bytes: int
    quota_gigabytes: float
    used_bytes: int
    quota_used_percent: float
    active_session_count: int
    created_at: datetime
    last_login_at: Optional[datetime] = None

    @classmethod
    def from_usage(cls, usage: AccountUsage) -> "ManagedUserResponse":
        account = usage.account
        return cls(
            user_id=account.user_id,
            username=account.username,
            display_name=account.display_name,
            role=account.role.value,
            is_active=account.is_active,
            must_change_password=account.must_change_password,
            quota_bytes=account.quota_bytes,
            quota_gigabytes=account.quota_gigabytes,
            used_bytes=usage.used_bytes,
            quota_used_percent=usage.quota_used_percent,
            active_session_count=usage.active_session_count,
            created_at=account.created_at,
            last_login_at=account.last_login_at,
        )

    @classmethod
    def from_account(cls, account: UserAccount) -> "ManagedUserResponse":
        return cls(
            user_id=account.user_id,
            username=account.username,
            display_name=account.display_name,
            role=account.role.value,
            is_active=account.is_active,
            must_change_password=account.must_change_password,
            quota_bytes=account.quota_bytes,
            quota_gigabytes=account.quota_gigabytes,
            used_bytes=0,
            quota_used_percent=0.0,
            active_session_count=0,
            created_at=account.created_at,
            last_login_at=account.last_login_at,
        )


class CreateUserRequest(BaseModel):
    """Create a new account; the initial password may be generated."""

    username: str = Field(..., min_length=3, max_length=64)
    display_name: str = Field(default="", max_length=120)
    role: str = Field(default=UserRole.RESEARCHER.value)
    quota_gigabytes: Optional[int] = Field(default=None, ge=0, le=100_000)
    initial_password: Optional[str] = Field(default=None, max_length=256)
    require_password_change: bool = True

    def parsed_role(self) -> UserRole:
        return UserRole.parse(self.role)

    def quota_bytes(self) -> Optional[int]:
        if self.quota_gigabytes is None:
            return None
        return self.quota_gigabytes * _BYTES_PER_GIGABYTE


class UpdateUserRequest(BaseModel):
    """Partial update; every field that stays ``None`` is left unchanged."""

    display_name: Optional[str] = Field(default=None, max_length=120)
    role: Optional[str] = None
    quota_gigabytes: Optional[int] = Field(default=None, ge=0, le=100_000)
    is_active: Optional[bool] = None

    def parsed_role(self) -> Optional[UserRole]:
        return UserRole.parse(self.role) if self.role else None

    def quota_bytes(self) -> Optional[int]:
        if self.quota_gigabytes is None:
            return None
        return self.quota_gigabytes * _BYTES_PER_GIGABYTE


class ResetPasswordRequest(BaseModel):
    """Set a new password for somebody else."""

    new_password: Optional[str] = Field(default=None, max_length=256)
    require_password_change: bool = True


class CreatedUserResponse(BaseModel):
    """Returned once, right after creating an account."""

    user: ManagedUserResponse
    initial_password: str


class PasswordResetResponse(BaseModel):
    """Returned once, right after resetting a password."""

    user_id: str
    username: str
    new_password: str


class UserSessionResponse(BaseModel):
    """One active browser session of a managed user."""

    session_id_preview: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: Optional[datetime]
    client_description: str

    @classmethod
    def from_session(cls, session: LoginSession) -> "UserSessionResponse":
        return cls(
            # Never expose the full id; it is the hash of a live cookie.
            session_id_preview=session.session_id[:12],
            created_at=session.created_at,
            expires_at=session.expires_at,
            last_seen_at=session.last_seen_at,
            client_description=session.client_description,
        )


class AuditEventResponse(BaseModel):
    """One line of the administrative audit trail."""

    event_id: int
    occurred_at: datetime
    actor_username: Optional[str]
    action: str
    subject: Optional[str]
    detail: str

    @classmethod
    def from_event(cls, event: AuditEvent) -> "AuditEventResponse":
        return cls(
            event_id=event.event_id,
            occurred_at=event.occurred_at,
            actor_username=event.actor_username,
            action=event.action,
            subject=event.subject,
            detail=event.detail,
        )


class RevokedSessionsResponse(BaseModel):
    """How many sessions an administrator just terminated."""

    user_id: str
    revoked_session_count: int


class UserListResponse(BaseModel):
    """The whole user administration table."""

    users: List[ManagedUserResponse]
