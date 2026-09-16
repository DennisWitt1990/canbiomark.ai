"""Sign in, sign out and password self service."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, Response

from ...container import ServiceContainer
from ...domain.user_account import UserAccount
from ..cookies import SessionCookieWriter
from ..dependencies import get_container, get_current_user, get_session_cookie
from ..schemas.authentication_schemas import (
    ChangePasswordRequest,
    CurrentUserResponse,
    LoginRequest,
    PasswordPolicyResponse,
    SimpleAcknowledgement,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _describe_client(request: Request) -> str:
    """A short, non-identifying description stored with the session."""
    user_agent = request.headers.get("user-agent", "unknown client")
    return user_agent[:200]


@router.post("/login", response_model=CurrentUserResponse)
def login(
    login_request: LoginRequest,
    response: Response,
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> CurrentUserResponse:
    """Verify username and password, then open a session cookie."""
    authenticated = container.authentication_service.login(
        username=login_request.username,
        password=login_request.password,
        client_description=_describe_client(request),
    )
    SessionCookieWriter(container.settings).attach(
        response, authenticated.session_cookie_value
    )
    return CurrentUserResponse.from_account(authenticated.account)


@router.post("/logout", response_model=SimpleAcknowledgement)
def logout(
    response: Response,
    session_cookie: Optional[str] = Depends(get_session_cookie),
    container: ServiceContainer = Depends(get_container),
) -> SimpleAcknowledgement:
    """Revoke the current session and clear the cookie."""
    container.authentication_service.logout(session_cookie)
    SessionCookieWriter(container.settings).clear(response)
    return SimpleAcknowledgement(message="Signed out.")


@router.get("/me", response_model=CurrentUserResponse)
def read_current_user(
    current_user: UserAccount = Depends(get_current_user),
) -> CurrentUserResponse:
    """The account behind the current session; used by the frontend auth gate."""
    return CurrentUserResponse.from_account(current_user)


@router.post("/change-password", response_model=SimpleAcknowledgement)
def change_own_password(
    change_request: ChangePasswordRequest,
    response: Response,
    current_user: UserAccount = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> SimpleAcknowledgement:
    """Rotate the own password; this signs every session of this user out."""
    container.authentication_service.change_own_password(
        current_user,
        change_request.current_password,
        change_request.new_password,
    )
    SessionCookieWriter(container.settings).clear(response)
    return SimpleAcknowledgement(
        message="Password changed. Please sign in again with the new password."
    )


@router.get("/password-policy", response_model=PasswordPolicyResponse)
def read_password_policy(
    container: ServiceContainer = Depends(get_container),
) -> PasswordPolicyResponse:
    """Shown next to password fields so the rules are visible before submitting."""
    policy = container.password_policy
    return PasswordPolicyResponse(
        minimum_length=policy.minimum_length, description=policy.describe()
    )
