"""A thread-safe, in-memory registry of user-owned jobs.

Both the tissue batch runner and the AI suite keep their job state here.  The
registry enforces ownership, so a caller can never see or cancel a job that
belongs to somebody else.
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, Generic, List, Optional, Protocol, TypeVar

from ..domain.errors import AuthorizationError, ResourceNotFoundError


class OwnedJob(Protocol):
    """Everything the registry needs to know about a job."""

    job_id: str
    owner_user_id: str


JobType = TypeVar("JobType", bound=OwnedJob)


class JobRegistry(Generic[JobType]):
    """Stores jobs by id and guards concurrent access with a single lock."""

    def __init__(self, job_kind: str) -> None:
        self._job_kind = job_kind
        self._jobs_by_id: Dict[str, JobType] = {}
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """Exposed so a worker can perform a compound read-modify-write."""
        return self._lock

    def register(self, job: JobType) -> JobType:
        with self._lock:
            self._jobs_by_id[job.job_id] = job
        return job

    def get_for_owner(self, job_id: str, owner_user_id: str) -> JobType:
        """Return a job, or raise if it is unknown or owned by somebody else."""
        with self._lock:
            job = self._jobs_by_id.get(job_id)

        if job is None:
            raise ResourceNotFoundError(f"Unknown {self._job_kind}: {job_id}")
        if job.owner_user_id != owner_user_id:
            raise AuthorizationError(f"This {self._job_kind} belongs to another user.")
        return job

    def find(self, job_id: str) -> Optional[JobType]:
        with self._lock:
            return self._jobs_by_id.get(job_id)

    def list_for_owner(
        self, owner_user_id: str, sort_key: Optional[Callable[[JobType], float]] = None
    ) -> List[JobType]:
        with self._lock:
            jobs = [
                job
                for job in self._jobs_by_id.values()
                if job.owner_user_id == owner_user_id
            ]
        if sort_key is not None:
            jobs.sort(key=sort_key, reverse=True)
        return jobs

    def remove(self, job_id: str) -> Optional[JobType]:
        with self._lock:
            return self._jobs_by_id.pop(job_id, None)

    def update(self, job_id: str, **attributes) -> Optional[JobType]:
        """Apply attribute changes under the lock and refresh ``updated_at``."""
        with self._lock:
            job = self._jobs_by_id.get(job_id)
            if job is None:
                return None
            for attribute_name, value in attributes.items():
                setattr(job, attribute_name, value)
            touch = getattr(job, "touch", None)
            if callable(touch):
                touch()
            return job
