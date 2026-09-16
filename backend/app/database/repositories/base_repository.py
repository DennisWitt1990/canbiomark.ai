"""Shared helpers for all repositories."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..connection import DatabaseConnectionFactory


class BaseRepository:
    """Holds the connection factory and timestamp conversion helpers."""

    def __init__(self, connection_factory: DatabaseConnectionFactory) -> None:
        self._connection_factory = connection_factory

    @staticmethod
    def current_timestamp() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def to_stored_timestamp(cls, moment: Optional[datetime]) -> Optional[str]:
        if moment is None:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).isoformat()

    @staticmethod
    def from_stored_timestamp(raw_value: Optional[str]) -> Optional[datetime]:
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
