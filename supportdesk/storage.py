"""SQLite persistence for tickets and agent run outputs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from supportdesk.models import Ticket, TriageResult, utc_now


class TicketStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_updated_at ON tickets(updated_at DESC)"
            )

    def save_result(self, result: TriageResult) -> dict[str, Any]:
        payload = result.to_dict()
        ticket = result.ticket
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tickets (
                    id,
                    subject,
                    message,
                    customer_email,
                    source,
                    created_at,
                    updated_at,
                    result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    subject = excluded.subject,
                    message = excluded.message,
                    customer_email = excluded.customer_email,
                    source = excluded.source,
                    updated_at = excluded.updated_at,
                    result_json = excluded.result_json
                """,
                (
                    ticket.id,
                    ticket.subject,
                    ticket.message,
                    ticket.customer_email,
                    ticket.source,
                    ticket.created_at,
                    utc_now(),
                    json.dumps(payload),
                ),
            )
        return payload

    def list_tickets(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, subject, customer_email, source, created_at, updated_at, result_json
                FROM tickets
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        summaries: list[dict[str, Any]] = []
        for row in rows:
            result = json.loads(row["result_json"])
            summaries.append(
                {
                    "id": row["id"],
                    "subject": row["subject"],
                    "customer_email": row["customer_email"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "category": result["intake"]["data"]["category"],
                    "priority": result["intake"]["data"]["priority"],
                    "owner_team": result["routing"]["data"]["owner_team"],
                    "sla": result["routing"]["data"]["sla"],
                    "quality_score": result["quality"]["data"]["quality_score"],
                    "recommended_action": result["routing"]["data"]["recommended_action"],
                }
            )
        return summaries

    def get_result(self, ticket_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM tickets WHERE id = ?",
                (ticket_id,),
            ).fetchone()

        if row is None:
            return None
        return json.loads(row["result_json"])

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, subject, message, customer_email, source, created_at
                FROM tickets
                WHERE id = ?
                """,
                (ticket_id,),
            ).fetchone()

        if row is None:
            return None
        return Ticket(
            id=row["id"],
            subject=row["subject"],
            message=row["message"],
            customer_email=row["customer_email"],
            source=row["source"],
            created_at=row["created_at"],
        )
