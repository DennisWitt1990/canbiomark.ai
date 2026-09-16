"""Everything an administrator can do to other accounts.

This is the replacement for the old invite-code flow: instead of generating a
token and mailing it around, an administrator creates the account directly,
hands over the initial password once, and can afterwards disable it, change its
quota or role, reset its password, or delete it together with its workspace.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from ..domain.errors import ResourceNotFoundError, ValidationError
from ..domain.login_session import LoginSession
from ..domain.user_account import UserAccount, UserRole
from ..database.repositories.audit_repository import AuditEvent, AuditRepository
from ..database.repositories.session_repository import SessionRepository
from ..database.repositories.user_repository import UserRepository
from ..security.password_hasher import PasswordHasher
from ..security.password_policy import PasswordPolicy
from .workspace_service import WorkspaceService


@dataclass(frozen=True)
class CreatedAccount:
    """A newly created account plus the one-time initial password."""

    account: UserAccount
    initial_password: str


@dataclass(frozen=True)
class AccountUsage:
    """An account enriched with the disk usage of its workspace."""

    account: UserAccount
    used_bytes: int
    active_session_count: int

    @property
    def quota_used_percent(self) -> float:
        if self.account.quota_bytes <= 0:
            return 0.0
        return round(self.used_bytes / self.account.quota_bytes * 100, 1)


class UserAdministrationService:
    """Administrative use cases; every method expects an already authorized caller."""

    def __init__(
        self,
        *,
        user_repository: UserRepository,
        session_repository: SessionRepository,
        audit_repository: AuditRepository,
        workspace_service: WorkspaceService,
        password_hasher: PasswordHasher,
        password_policy: PasswordPolicy,
        default_quota_bytes: int,
    ) -> None:
        self._user_repository = user_repository
        self._session_repository = session_repository
        self._audit_repository = audit_repository
        self._workspace_service = workspace_service
        self._password_hasher = password_hasher
        self._password_policy = password_policy
        self._default_quota_bytes = default_quota_bytes

    # -- reading -----------------------------------------------------------

    def list_accounts(self) -> List[AccountUsage]:
        accounts = self._user_repository.list_all()
        usages: List[AccountUsage] = []
        for account in accounts:
            workspace = self._workspace_service.for_user(account.user_id)
            usages.append(
                AccountUsage(
                    account=account,
                    used_bytes=workspace.used_bytes(),
                    active_session_count=len(
                        self._session_repository.list_for_user(account.user_id)
                    ),
                )
            )
        return usages

    def get_account(self, user_id: str) -> UserAccount:
        account = self._user_repository.find_by_id(user_id)
        if account is None:
            raise ResourceNotFoundError("This user account does not exist.")
        return account

    def list_sessions(self, user_id: str) -> List[LoginSession]:
        self.get_account(user_id)
        return self._session_repository.list_for_user(user_id)

    def list_audit_events(self, limit: int = 100) -> List[AuditEvent]:
        return self._audit_repository.list_recent(limit)

    # -- writing -----------------------------------------------------------

    def create_account(
        self,
        *,
        administrator: UserAccount,
        username: str,
        display_name: str,
        role: UserRole,
        quota_bytes: Optional[int] = None,
        initial_password: Optional[str] = None,
        require_password_change: bool = True,
    ) -> CreatedAccount:
        try:
            normalized_username = UserAccount.normalize_username(username)
        except ValueError as error:
            raise ValidationError(str(error)) from error

        if self._user_repository.username_exists(normalized_username):
            raise ValidationError(
                f"The username '{normalized_username}' is already taken."
            )

        password = initial_password or self._password_policy.generate()
        self._password_policy.validate(password)

        account = self._user_repository.insert(
            username=normalized_username,
            display_name=display_name or normalized_username,
            role=role,
            password_hash=self._password_hasher.hash_password(password),
            quota_bytes=quota_bytes if quota_bytes is not None else self._default_quota_bytes,
            must_change_password=require_password_change,
        )
        # Create the workspace eagerly so quota reporting works right away.
        self._workspace_service.for_user(account.user_id)

        self._audit_repository.record(
            actor_username=administrator.username,
            action="user.created",
            subject=account.username,
            detail=f"role={role.value}",
        )
        return CreatedAccount(account=account, initial_password=password)

    def update_account(
        self,
        *,
        administrator: UserAccount,
        user_id: str,
        display_name: Optional[str] = None,
        role: Optional[UserRole] = None,
        quota_bytes: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> UserAccount:
        target_account = self.get_account(user_id)

        if role is not None and role is not UserRole.ADMINISTRATOR:
            self._assert_not_last_administrator(target_account, "change its role")
        if is_active is False:
            self._assert_not_last_administrator(target_account, "disable it")
        if quota_bytes is not None and quota_bytes < 0:
            raise ValidationError("The quota must not be negative.")

        self._user_repository.update_profile(
            user_id,
            display_name=display_name,
            role=role,
            quota_bytes=quota_bytes,
            is_active=is_active,
        )

        # A disabled account must lose its running sessions immediately.
        if is_active is False:
            self._session_repository.revoke_all_for_user(user_id)

        self._audit_repository.record(
            actor_username=administrator.username,
            action="user.updated",
            subject=target_account.username,
            detail=self._describe_changes(display_name, role, quota_bytes, is_active),
        )
        return self.get_account(user_id)

    def reset_password(
        self,
        *,
        administrator: UserAccount,
        user_id: str,
        new_password: Optional[str] = None,
        require_password_change: bool = True,
    ) -> str:
        """Set a new password and return it once, for the administrator to pass on."""
        target_account = self.get_account(user_id)

        password = new_password or self._password_policy.generate()
        self._password_policy.validate(password)

        self._user_repository.update_password(
            user_id,
            self._password_hasher.hash_password(password),
            must_change_password=require_password_change,
        )
        self._session_repository.revoke_all_for_user(user_id)

        self._audit_repository.record(
            actor_username=administrator.username,
            action="user.password_reset",
            subject=target_account.username,
        )
        return password

    def revoke_sessions(self, *, administrator: UserAccount, user_id: str) -> int:
        target_account = self.get_account(user_id)
        revoked_count = self._session_repository.revoke_all_for_user(user_id)
        self._audit_repository.record(
            actor_username=administrator.username,
            action="user.sessions_revoked",
            subject=target_account.username,
            detail=f"{revoked_count} session(s)",
        )
        return revoked_count

    def delete_account(
        self,
        *,
        administrator: UserAccount,
        user_id: str,
        delete_workspace: bool = True,
    ) -> None:
        target_account = self.get_account(user_id)

        if target_account.user_id == administrator.user_id:
            raise ValidationError("You cannot delete your own account.")
        self._assert_not_last_administrator(target_account, "delete it")

        self._user_repository.delete(user_id)
        if delete_workspace:
            self._workspace_service.delete_for_user(user_id)

        self._audit_repository.record(
            actor_username=administrator.username,
            action="user.deleted",
            subject=target_account.username,
            detail="workspace deleted" if delete_workspace else "workspace kept",
        )

    # -- guards ------------------------------------------------------------

    def _assert_not_last_administrator(
        self, target_account: UserAccount, attempted_action: str
    ) -> None:
        """Never leave the installation without a usable administrator."""
        if not target_account.is_administrator or not target_account.is_active:
            return
        if self._user_repository.count_active_administrators() <= 1:
            raise ValidationError(
                "This is the last active administrator; you cannot "
                f"{attempted_action}."
            )

    @staticmethod
    def _describe_changes(
        display_name: Optional[str],
        role: Optional[UserRole],
        quota_bytes: Optional[int],
        is_active: Optional[bool],
    ) -> str:
        changes: List[str] = []
        if display_name is not None:
            changes.append(f"display_name={display_name!r}")
        if role is not None:
            changes.append(f"role={role.value}")
        if quota_bytes is not None:
            changes.append(f"quota_bytes={quota_bytes}")
        if is_active is not None:
            changes.append(f"is_active={is_active}")
        return ", ".join(changes)
