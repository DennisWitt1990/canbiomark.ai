"""Domain model: plain objects with behaviour, free of FastAPI and SQLite."""

from .user_account import UserAccount, UserRole
from .login_session import LoginSession
from .experiment import Experiment, CellTypeSelection
from .job import JobStatus, JobProgress
from .simbu import SimBuParameters, SimBuRunResult, BatchTask, BatchJob
from .errors import (
    DomainError,
    AuthenticationError,
    AuthorizationError,
    PasswordPolicyError,
    ResourceNotFoundError,
    ValidationError,
    WorkspaceViolationError,
)

__all__ = [
    "UserAccount",
    "UserRole",
    "LoginSession",
    "Experiment",
    "CellTypeSelection",
    "JobStatus",
    "JobProgress",
    "SimBuParameters",
    "SimBuRunResult",
    "BatchTask",
    "BatchJob",
    "DomainError",
    "AuthenticationError",
    "AuthorizationError",
    "PasswordPolicyError",
    "ResourceNotFoundError",
    "ValidationError",
    "WorkspaceViolationError",
]
