"""Declarative schema creation.

The previous implementation stored bearer tokens in a ``tokens`` table.  This
schema replaces that with real accounts (``users`` carries a salted password
hash) plus short-lived ``login_sessions``.
"""
from __future__ import annotations

from typing import List

from .connection import DatabaseConnectionFactory

_SCHEMA_STATEMENTS: List[str] = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id              TEXT PRIMARY KEY,
        username             TEXT NOT NULL UNIQUE,
        display_name         TEXT NOT NULL DEFAULT '',
        role                 TEXT NOT NULL,
        password_hash        TEXT NOT NULL,
        password_salt        TEXT NOT NULL,
        password_iterations  INTEGER NOT NULL,
        quota_bytes          INTEGER NOT NULL,
        is_active            INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        created_at           TEXT NOT NULL,
        last_login_at        TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS login_sessions (
        session_id         TEXT PRIMARY KEY,
        user_id            TEXT NOT NULL,
        created_at         TEXT NOT NULL,
        expires_at         TEXT NOT NULL,
        last_seen_at       TEXT,
        revoked_at         TEXT,
        client_description TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON login_sessions (user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON login_sessions (expires_at);",
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        occurred_at TEXT NOT NULL,
        actor_user  TEXT,
        action      TEXT NOT NULL,
        subject     TEXT,
        detail      TEXT NOT NULL DEFAULT ''
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_events (occurred_at DESC);",
]


class SchemaInitializer:
    """Creates all tables and indexes if they do not exist yet."""

    def __init__(self, connection_factory: DatabaseConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def initialize(self) -> None:
        with self._connection_factory.write_transaction() as connection:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
