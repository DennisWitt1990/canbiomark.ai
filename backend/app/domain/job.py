"""Shared vocabulary for long-running background work."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class JobStatus(str, Enum):
    """Life cycle of any background job in the application."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FINISHED_WITH_ERRORS = "finished_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {
            JobStatus.FINISHED,
            JobStatus.FINISHED_WITH_ERRORS,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }

    @property
    def has_results(self) -> bool:
        return self in {JobStatus.FINISHED, JobStatus.FINISHED_WITH_ERRORS}


@dataclass
class JobProgress:
    """Coarse progress report shown in the user interface."""

    completed_fraction: float = 0.0
    message: str = ""

    @property
    def completed_percent(self) -> float:
        return round(self.completed_fraction * 100, 1)

    def update(self, completed_fraction: float, message: str) -> None:
        self.completed_fraction = max(0.0, min(1.0, completed_fraction))
        self.message = message
