"""Domain level exceptions.

Services raise these; the API layer translates them into HTTP responses in
exactly one place (``app.api.error_handlers``).  Services therefore never
import FastAPI.
"""
from __future__ import annotations


class DomainError(Exception):
    """Base class for every expected, user-facing error condition."""

    http_status_code: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    """The caller supplied input that cannot be processed."""

    http_status_code = 400


class AuthenticationError(DomainError):
    """The caller is unknown or supplied wrong credentials."""

    http_status_code = 401


class AuthorizationError(DomainError):
    """The caller is known but lacks the required role or ownership."""

    http_status_code = 403


class ResourceNotFoundError(DomainError):
    """A requested user, job or file does not exist."""

    http_status_code = 404


class PasswordPolicyError(ValidationError):
    """A password does not satisfy the configured policy."""


class WorkspaceViolationError(AuthorizationError):
    """A path escapes the workspace of the requesting user."""
