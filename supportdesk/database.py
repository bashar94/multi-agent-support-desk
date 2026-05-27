"""Database backend selection."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from supportdesk.storage import TicketStore


def build_ticket_store(default_db_path: Path) -> TicketStore:
    database_url = os.environ.get("SUPPORT_DESK_DATABASE_URL", "").strip()
    if not database_url:
        return TicketStore(default_db_path)

    parsed = urlparse(database_url)
    if parsed.scheme in {"", "sqlite"}:
        return TicketStore(_sqlite_path_from_url(database_url, default_db_path))

    if parsed.scheme in {"postgres", "postgresql"}:
        from supportdesk.postgres import PostgresTicketStore

        return PostgresTicketStore(database_url)

    raise ValueError("SUPPORT_DESK_DATABASE_URL must use sqlite://, postgres://, or postgresql://")


def _sqlite_path_from_url(database_url: str, default_db_path: Path) -> Path:
    if database_url == "sqlite:///:memory:":
        return Path(":memory:")

    parsed = urlparse(database_url)
    if not parsed.scheme:
        return Path(database_url)

    raw_path = unquote(parsed.path or "")
    if not raw_path:
        return default_db_path
    if parsed.netloc:
        raw_path = f"/{parsed.netloc}{raw_path}"
    while raw_path.startswith("//"):
        raw_path = raw_path[1:]
    return Path(raw_path)
