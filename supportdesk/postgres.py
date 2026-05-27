"""Optional Postgres persistence backend.

This module is imported only when SUPPORT_DESK_DATABASE_URL uses a Postgres URL.
It expects a DB-API compatible psycopg installation but keeps psycopg optional
for the default dependency-free SQLite demo.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from supportdesk.storage import TicketStore


class PostgresTicketStore(TicketStore):
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._init_schema()

    def _connect(self) -> Any:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "Postgres support requires installing the optional psycopg package."
            ) from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _execute(self, connection: Any, statement: str, params: tuple[Any, ...] = ()) -> Any:
        return connection.execute(statement.replace("?", "%s"), params)

    def _ensure_column(self, connection: Any, column: str, definition: str) -> None:
        row = self._execute(
            connection,
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = ? AND column_name = ?
            """,
            ("tickets", column),
        ).fetchone()
        if row is None:
            self._execute(connection, f"ALTER TABLE tickets ADD COLUMN {column} {definition}")
