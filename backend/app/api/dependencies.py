"""FastAPI dependencies.

These are the only functions that know both about HTTP and about the service
container.  They resolve the session cookie into a :class:`UserAccount` and
enforce the administrator role.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, Request

from ..config.settings import ApplicationSettings
from ..container import ServiceContainer
from ..domain.user_account import UserAccount
from ..services.workspace_service import UserWorkspace


def get_container(request: Request) -> ServiceContainer:
    """Return the container that ``create_application`` stored on the app."""
    return request.app.state.container


def get_settings_dependency(
    container: ServiceContainer = Depends(get_container),
) -> ApplicationSettings:
    return container.settings


def get_session_cookie(
    request: Request,
    container: ServiceContainer = Depends(get_container),
) -> Optional[str]:
    """Read the session cookie under its configured name."""
    return request.cookies.get(container.settings.session_cookie_name)


def get_current_user(
    session_cookie: Optional[str] = Depends(get_session_cookie),
    container: ServiceContainer = Depends(get_container),
) -> UserAccount:
    """Resolve the signed-in account, or raise 401."""
    return container.authentication_service.resolve_session(session_cookie)


def get_current_administrator(
    current_user: UserAccount = Depends(get_current_user),
) -> UserAccount:
    """Resolve the signed-in account and require the administrator role."""
    current_user.require_administrator()
    return current_user


def get_current_workspace(
    current_user: UserAccount = Depends(get_current_user),
    container: ServiceContainer = Depends(get_container),
) -> UserWorkspace:
    """The private file workspace of the signed-in user."""
    return container.workspace_service.for_user(current_user.user_id)


# ``Cookie`` is imported for documentation purposes in the OpenAPI schema.
__all__ = [
    "Cookie",
    "get_container",
    "get_settings_dependency",
    "get_session_cookie",
    "get_current_user",
    "get_current_administrator",
    "get_current_workspace",
]
