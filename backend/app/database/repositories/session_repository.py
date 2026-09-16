"""Persistence for :class:`~app.domain.login_session.LoginSession`."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from ...domain.login_session import LoginSession
from .base_repository import BaseRepository

_SESSION_COLUMNS = (
    "session_id, user_id, created_at, expires_at, last_seen_at, revoked_at, "
    "client_description"
)


class SessionRepository(BaseRepository):
    """Stores hashed session identifiers and their validity window."""

    def create(
        self,
        *,
        session_id: str,
        user_id: str,
        lifetime_seconds: int,
        client_description: str = "",
    ) -> LoginSession:
        created_at = self.current_timestamp()
        expires_at = created_at + timedelta(seconds=lifetime_seconds)

        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                """
                INSERT INTO login_sessions (
                    session_id, user_id, created_at, expires_at,
                    last_seen_at, revoked_at, client_description
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    session_id,
                    user_id,
                    self.to_stored_timestamp(created_at),
                    self.to_stored_timestamp(expires_at),
                    self.to_stored_timestamp(created_at),
                    client_description[:200],
                ),
            )

        return LoginSession(
            session_id=session_id,
            user_id=user_id,
            created_at=created_at,
            expires_at=expires_at,
            last_seen_at=created_at,
            revoked_at=None,
            client_description=client_description[:200],
        )

    def find_by_id(self, session_id: str) -> Optional[LoginSession]:
        with self._connection_factory.read_connection() as connection:
            row = connection.execute(
                f"SELECT {_SESSION_COLUMNS} FROM login_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return self._to_session(row) if row else None

    def list_for_user(self, user_id: str, include_revoked: bool = False) -> List[LoginSession]:
        query = f"SELECT {_SESSION_COLUMNS} FROM login_sessions WHERE user_id = ?"
        if not include_revoked:
            query += " AND revoked_at IS NULL"
        query += " ORDER BY created_at DESC"

        with self._connection_factory.read_connection() as connection:
            rows = connection.execute(query, (user_id,)).fetchall()
        return [self._to_session(row) for row in rows]

    def touch(self, session_id: str, moment: Optional[datetime] = None) -> None:
        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                "UPDATE login_sessions SET last_seen_at = ? WHERE session_id = ?",
                (self.to_stored_timestamp(moment or self.current_timestamp()), session_id),
            )

    def revoke(self, session_id: str) -> None:
        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                "UPDATE login_sessions SET revoked_at = ? "
                "WHERE session_id = ? AND revoked_at IS NULL",
                (self.to_stored_timestamp(self.current_timestamp()), session_id),
            )

    def revoke_all_for_user(self, user_id: str) -> int:
        with self._connection_factory.write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE login_sessions SET revoked_at = ? "
                "WHERE user_id = ? AND revoked_at IS NULL",
                (self.to_stored_timestamp(self.current_timestamp()), user_id),
            )
            return cursor.rowcount

    def delete_expired(self) -> int:
        """Housekeeping: drop sessions that expired more than a day ago."""
        cutoff = self.current_timestamp() - timedelta(days=1)
        with self._connection_factory.write_transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM login_sessions WHERE expires_at < ?",
                (self.to_stored_timestamp(cutoff),),
            )
            return cursor.rowcount

    @classmethod
    def _to_session(cls, row: sqlite3.Row) -> LoginSession:
        return LoginSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            created_at=cls.from_stored_timestamp(row["created_at"])
            or cls.current_timestamp(),
            expires_at=cls.from_stored_timestamp(row["expires_at"])
            or cls.current_timestamp(),
            last_seen_at=cls.from_stored_timestamp(row["last_seen_at"]),
            revoked_at=cls.from_stored_timestamp(row["revoked_at"]),
            client_description=row["client_description"] or "",
        )
