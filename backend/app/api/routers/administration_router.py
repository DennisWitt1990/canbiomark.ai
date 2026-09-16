"""User administration.

Every endpoint here requires the administrator role, enforced once through the
router-level dependency.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query

from ...container import ServiceContainer
from ...domain.user_account import UserAccount
from ..dependencies import get_container, get_current_administrator
from ..schemas.administration_schemas import (
    AuditEventResponse,
    CreateUserRequest,
    CreatedUserResponse,
    ManagedUserResponse,
    PasswordResetResponse,
    ResetPasswordRequest,
    RevokedSessionsResponse,
    UpdateUserRequest,
    UserListResponse,
    UserSessionResponse,
)
from ..schemas.authentication_schemas import SimpleAcknowledgement

router = APIRouter(
    prefix="/admin",
    tags=["administration"],
    dependencies=[Depends(get_current_administrator)],
)


@router.get("/users", response_model=UserListResponse)
def list_users(
    container: ServiceContainer = Depends(get_container),
) -> UserListResponse:
    """All accounts with their disk usage and session count."""
    usages = container.user_administration_service.list_accounts()
    return UserListResponse(
        users=[ManagedUserResponse.from_usage(usage) for usage in usages]
    )


@router.post("/users", response_model=CreatedUserResponse, status_code=201)
def create_user(
    create_request: CreateUserRequest,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> CreatedUserResponse:
    """Create an account and return its initial password exactly once."""
    created = container.user_administration_service.create_account(
        administrator=administrator,
        username=create_request.username,
        display_name=create_request.display_name,
        role=create_request.parsed_role(),
        quota_bytes=create_request.quota_bytes(),
        initial_password=create_request.initial_password,
        require_password_change=create_request.require_password_change,
    )
    return CreatedUserResponse(
        user=ManagedUserResponse.from_account(created.account),
        initial_password=created.initial_password,
    )


@router.patch("/users/{user_id}", response_model=ManagedUserResponse)
def update_user(
    user_id: str,
    update_request: UpdateUserRequest,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> ManagedUserResponse:
    """Change display name, role, quota or the active flag."""
    updated_account = container.user_administration_service.update_account(
        administrator=administrator,
        user_id=user_id,
        display_name=update_request.display_name,
        role=update_request.parsed_role(),
        quota_bytes=update_request.quota_bytes(),
        is_active=update_request.is_active,
    )
    return ManagedUserResponse.from_account(updated_account)


@router.post("/users/{user_id}/password", response_model=PasswordResetResponse)
def reset_user_password(
    user_id: str,
    reset_request: ResetPasswordRequest,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> PasswordResetResponse:
    """Set a new password and hand it back once, for the administrator to pass on."""
    administration_service = container.user_administration_service
    new_password = administration_service.reset_password(
        administrator=administrator,
        user_id=user_id,
        new_password=reset_request.new_password,
        require_password_change=reset_request.require_password_change,
    )
    account = administration_service.get_account(user_id)
    return PasswordResetResponse(
        user_id=account.user_id,
        username=account.username,
        new_password=new_password,
    )


@router.get("/users/{user_id}/sessions", response_model=List[UserSessionResponse])
def list_user_sessions(
    user_id: str,
    container: ServiceContainer = Depends(get_container),
) -> List[UserSessionResponse]:
    """The active browser sessions of one account."""
    sessions = container.user_administration_service.list_sessions(user_id)
    return [UserSessionResponse.from_session(session) for session in sessions]


@router.delete("/users/{user_id}/sessions", response_model=RevokedSessionsResponse)
def revoke_user_sessions(
    user_id: str,
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> RevokedSessionsResponse:
    """Sign an account out everywhere, without changing its password."""
    revoked_count = container.user_administration_service.revoke_sessions(
        administrator=administrator, user_id=user_id
    )
    return RevokedSessionsResponse(
        user_id=user_id, revoked_session_count=revoked_count
    )


@router.delete("/users/{user_id}", response_model=SimpleAcknowledgement)
def delete_user(
    user_id: str,
    delete_workspace: bool = Query(
        default=True, description="Also delete the user's files on disk."
    ),
    administrator: UserAccount = Depends(get_current_administrator),
    container: ServiceContainer = Depends(get_container),
) -> SimpleAcknowledgement:
    """Delete an account, optionally together with its workspace."""
    container.user_administration_service.delete_account(
        administrator=administrator,
        user_id=user_id,
        delete_workspace=delete_workspace,
    )
    return SimpleAcknowledgement(message="The account was deleted.")


@router.get("/audit", response_model=List[AuditEventResponse])
def list_audit_events(
    limit: int = Query(default=100, ge=1, le=1000),
    container: ServiceContainer = Depends(get_container),
) -> List[AuditEventResponse]:
    """The most recent administrative actions."""
    events = container.user_administration_service.list_audit_events(limit)
    return [AuditEventResponse.from_event(event) for event in events]
