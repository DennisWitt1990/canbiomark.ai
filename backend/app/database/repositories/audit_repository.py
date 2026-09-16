"""Append-only log of administrative actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .base_repository import BaseRepository


@dataclass(frozen=True)
class AuditEvent:
    """One recorded administrative action."""

    event_id: int
    occurred_at: datetime
    actor_username: Optional[str]
    action: str
    subject: Optional[str]
    detail: str


class AuditRepository(BaseRepository):
    """Writes and reads the administrative audit trail."""

    def record(
        self,
        *,
        actor_username: Optional[str],
        action: str,
        subject: Optional[str] = None,
        detail: str = "",
    ) -> None:
        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                """
                INSERT INTO audit_events (occurred_at, actor_user, action, subject, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self.to_stored_timestamp(self.current_timestamp()),
                    actor_username,
                    action,
                    subject,
                    detail[:1000],
                ),
            )

    def list_recent(self, limit: int = 100) -> List[AuditEvent]:
        with self._connection_factory.read_connection() as connection:
            rows = connection.execute(
                "SELECT event_id, occurred_at, actor_user, action, subject, detail "
                "FROM audit_events ORDER BY occurred_at DESC, event_id DESC LIMIT ?",
                (max(1, min(limit, 1000)),),
            ).fetchall()

        return [
            AuditEvent(
                event_id=int(row["event_id"]),
                occurred_at=self.from_stored_timestamp(row["occurred_at"])
                or self.current_timestamp(),
                actor_username=row["actor_user"],
                action=row["action"],
                subject=row["subject"],
                detail=row["detail"] or "",
            )
            for row in rows
        ]
