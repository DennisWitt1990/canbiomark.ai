"""Persistence for :class:`~app.domain.user_account.UserAccount`."""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ...domain.user_account import UserAccount, UserRole
from ...security.password_hasher import PasswordHash
from .base_repository import BaseRepository

_ACCOUNT_COLUMNS = (
    "user_id, username, display_name, role, quota_bytes, is_active, "
    "must_change_password, created_at, last_login_at"
)


@dataclass(frozen=True)
class StoredUserRecord:
    """An account together with its password hash, as stored in SQLite."""

    account: UserAccount
    password_hash: PasswordHash


class UserRepository(BaseRepository):
    """Create, read, update and delete user accounts."""

    # -- reading -----------------------------------------------------------

    def find_by_username(self, username: str) -> Optional[StoredUserRecord]:
        normalized_username = UserAccount.normalize_username(username)
        with self._connection_factory.read_connection() as connection:
            row = connection.execute(
                f"SELECT {_ACCOUNT_COLUMNS}, password_hash, password_salt, "
                "password_iterations FROM users WHERE username = ?",
                (normalized_username,),
            ).fetchone()
        return self._to_stored_record(row) if row else None

    def find_by_id(self, user_id: str) -> Optional[UserAccount]:
        with self._connection_factory.read_connection() as connection:
            row = connection.execute(
                f"SELECT {_ACCOUNT_COLUMNS} FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._to_account(row) if row else None

    def list_all(self) -> List[UserAccount]:
        with self._connection_factory.read_connection() as connection:
            rows = connection.execute(
                f"SELECT {_ACCOUNT_COLUMNS} FROM users ORDER BY username ASC"
            ).fetchall()
        return [self._to_account(row) for row in rows]

    def count_active_administrators(self) -> int:
        with self._connection_factory.read_connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM users "
                "WHERE role = ? AND is_active = 1",
                (UserRole.ADMINISTRATOR.value,),
            ).fetchone()
        return int(row["total"])

    def username_exists(self, username: str) -> bool:
        return self.find_by_username(username) is not None

    # -- writing -----------------------------------------------------------

    def insert(
        self,
        *,
        username: str,
        display_name: str,
        role: UserRole,
        password_hash: PasswordHash,
        quota_bytes: int,
        must_change_password: bool,
    ) -> UserAccount:
        normalized_username = UserAccount.normalize_username(username)
        account = UserAccount(
            user_id=str(uuid.uuid4()),
            username=normalized_username,
            display_name=(display_name or normalized_username).strip(),
            role=role,
            quota_bytes=int(quota_bytes),
            is_active=True,
            must_change_password=must_change_password,
            created_at=self.current_timestamp(),
            last_login_at=None,
        )

        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    user_id, username, display_name, role,
                    password_hash, password_salt, password_iterations,
                    quota_bytes, is_active, must_change_password,
                    created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    account.user_id,
                    account.username,
                    account.display_name,
                    account.role.value,
                    password_hash.hash_hex,
                    password_hash.salt_hex,
                    password_hash.iterations,
                    account.quota_bytes,
                    1,
                    1 if must_change_password else 0,
                    self.to_stored_timestamp(account.created_at),
                ),
            )
        return account

    def update_profile(
        self,
        user_id: str,
        *,
        display_name: Optional[str] = None,
        role: Optional[UserRole] = None,
        quota_bytes: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> None:
        assignments: List[str] = []
        parameters: List[object] = []

        if display_name is not None:
            assignments.append("display_name = ?")
            parameters.append(display_name.strip())
        if role is not None:
            assignments.append("role = ?")
            parameters.append(role.value)
        if quota_bytes is not None:
            assignments.append("quota_bytes = ?")
            parameters.append(int(quota_bytes))
        if is_active is not None:
            assignments.append("is_active = ?")
            parameters.append(1 if is_active else 0)

        if not assignments:
            return

        parameters.append(user_id)
        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE user_id = ?",
                tuple(parameters),
            )

    def update_password(
        self, user_id: str, password_hash: PasswordHash, must_change_password: bool
    ) -> None:
        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                """
                UPDATE users
                   SET password_hash = ?, password_salt = ?, password_iterations = ?,
                       must_change_password = ?
                 WHERE user_id = ?
                """,
                (
                    password_hash.hash_hex,
                    password_hash.salt_hex,
                    password_hash.iterations,
                    1 if must_change_password else 0,
                    user_id,
                ),
            )

    def record_login(self, user_id: str, moment: Optional[datetime] = None) -> None:
        with self._connection_factory.write_transaction() as connection:
            connection.execute(
                "UPDATE users SET last_login_at = ? WHERE user_id = ?",
                (self.to_stored_timestamp(moment or self.current_timestamp()), user_id),
            )

    def delete(self, user_id: str) -> None:
        with self._connection_factory.write_transaction() as connection:
            connection.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    # -- mapping -----------------------------------------------------------

    @classmethod
    def _to_account(cls, row: sqlite3.Row) -> UserAccount:
        return UserAccount(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"] or row["username"],
            role=UserRole.parse(row["role"]),
            quota_bytes=int(row["quota_bytes"]),
            is_active=bool(row["is_active"]),
            must_change_password=bool(row["must_change_password"]),
            created_at=cls.from_stored_timestamp(row["created_at"])
            or cls.current_timestamp(),
            last_login_at=cls.from_stored_timestamp(row["last_login_at"]),
        )

    @classmethod
    def _to_stored_record(cls, row: sqlite3.Row) -> StoredUserRecord:
        return StoredUserRecord(
            account=cls._to_account(row),
            password_hash=PasswordHash(
                hash_hex=row["password_hash"],
                salt_hex=row["password_salt"],
                iterations=int(row["password_iterations"]),
            ),
        )
