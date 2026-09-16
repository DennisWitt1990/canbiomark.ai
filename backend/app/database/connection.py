"""Connection handling for the SQLite database.

The factory owns the only ``sqlite3.connect`` call in the code base.  Callers
use it as a context manager, which guarantees commit-on-success and
rollback-on-error without any repository repeating that logic.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class DatabaseConnectionFactory:
    """Creates configured SQLite connections for a single database file."""

    def __init__(self, database_file: Path) -> None:
        self._database_file = Path(database_file)
        self._write_lock = threading.Lock()

    @property
    def database_file(self) -> Path:
        return self._database_file

    def _connect(self) -> sqlite3.Connection:
        self._database_file.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self._database_file,
            check_same_thread=False,
            isolation_level=None,
            timeout=30.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA busy_timeout = 30000;")
        return connection

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        """Open a connection for queries that do not modify data."""
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def write_transaction(self) -> Iterator[sqlite3.Connection]:
        """Open a serialized transaction; commits on success, rolls back on error."""
        with self._write_lock:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE;")
            try:
                yield connection
            except Exception:
                connection.execute("ROLLBACK;")
                raise
            else:
                connection.execute("COMMIT;")
            finally:
                connection.close()
