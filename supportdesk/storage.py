"""SQLite persistence for tickets and agent run outputs."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from supportdesk.models import ApprovalState, Ticket, TriageResult, utc_now


class TicketStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    message TEXT NOT NULL,
                    customer_email TEXT NOT NULL,
                    source TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approval_status TEXT NOT NULL DEFAULT 'pending',
                    approval_reviewer TEXT NOT NULL DEFAULT '',
                    approval_note TEXT NOT NULL DEFAULT '',
                    approval_updated_at TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_tickets_updated_at ON tickets(updated_at DESC)"
            )
            self._ensure_column(connection, "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(connection, "approval_status", "TEXT NOT NULL DEFAULT 'pending'")
            self._ensure_column(connection, "approval_reviewer", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "approval_note", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "approval_updated_at", "TEXT NOT NULL DEFAULT ''")

    def _ensure_column(self, connection: sqlite3.Connection, column: str, definition: str) -> None:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(tickets)").fetchall()}
        if column not in columns:
            connection.execute(f"ALTER TABLE tickets ADD COLUMN {column} {definition}")

    def save_result(self, result: TriageResult) -> dict[str, Any]:
        payload = result.to_dict()
        ticket = result.ticket
        approval = payload["approval"]
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO tickets (
                    id,
                    subject,
                    message,
                    customer_email,
                    source,
                    metadata_json,
                    created_at,
                    updated_at,
                    approval_status,
                    approval_reviewer,
                    approval_note,
                    approval_updated_at,
                    result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    subject = excluded.subject,
                    message = excluded.message,
                    customer_email = excluded.customer_email,
                    source = excluded.source,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at,
                    approval_status = excluded.approval_status,
                    approval_reviewer = excluded.approval_reviewer,
                    approval_note = excluded.approval_note,
                    approval_updated_at = excluded.approval_updated_at,
                    result_json = excluded.result_json
                """,
                (
                    ticket.id,
                    ticket.subject,
                    ticket.message,
                    ticket.customer_email,
                    ticket.source,
                    json.dumps(ticket.metadata),
                    ticket.created_at,
                    utc_now(),
                    approval["status"],
                    approval["reviewer"],
                    approval["note"],
                    approval["updated_at"],
                    json.dumps(payload),
                ),
            )
        return payload

    def list_tickets(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    subject,
                    customer_email,
                    source,
                    created_at,
                    updated_at,
                    approval_status,
                    result_json
                FROM tickets
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        summaries: list[dict[str, Any]] = []
        for row in rows:
            result = self._normalize_result(json.loads(row["result_json"]))
            summaries.append(
                {
                    "id": row["id"],
                    "subject": row["subject"],
                    "customer_email": row["customer_email"],
                    "source": row["source"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "approval_status": row["approval_status"] or result["approval"]["status"],
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
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    result_json,
                    approval_status,
                    approval_reviewer,
                    approval_note,
                    approval_updated_at
                FROM tickets
                WHERE id = ?
                """,
                (ticket_id,),
            ).fetchone()

        if row is None:
            return None
        result = self._normalize_result(json.loads(row["result_json"]))
        result["approval"] = {
            "status": row["approval_status"] or result["approval"]["status"],
            "reviewer": row["approval_reviewer"] or result["approval"]["reviewer"],
            "note": row["approval_note"] or result["approval"]["note"],
            "updated_at": row["approval_updated_at"] or result["approval"]["updated_at"],
            "send_ready": (row["approval_status"] or result["approval"]["status"]) == "approved",
        }
        return result

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT id, subject, message, customer_email, source, metadata_json, created_at
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
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
        )

    def update_approval(
        self,
        ticket_id: str,
        status: str,
        reviewer: str = "",
        note: str = "",
    ) -> dict[str, Any] | None:
        result = self.get_result(ticket_id)
        if result is None:
            return None

        approval = ApprovalState.from_payload(
            {
                "status": status,
                "reviewer": reviewer,
                "note": note,
            }
        ).to_dict()
        result["approval"] = approval
        self._apply_approval_to_triage(result, approval)

        with self._connection() as connection:
            connection.execute(
                """
                UPDATE tickets
                SET
                    approval_status = ?,
                    approval_reviewer = ?,
                    approval_note = ?,
                    approval_updated_at = ?,
                    updated_at = ?,
                    result_json = ?
                WHERE id = ?
                """,
                (
                    approval["status"],
                    approval["reviewer"],
                    approval["note"],
                    approval["updated_at"],
                    utc_now(),
                    json.dumps(result),
                    ticket_id,
                ),
            )
        return result

    def analytics(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = connection.execute("SELECT result_json, approval_status FROM tickets").fetchall()

        by_priority: Counter[str] = Counter()
        by_owner_team: Counter[str] = Counter()
        by_recommended_action: Counter[str] = Counter()
        by_sla: Counter[str] = Counter()
        by_approval_status: Counter[str] = Counter()
        quality_scores: list[int] = []

        for row in rows:
            result = self._normalize_result(json.loads(row["result_json"]))
            by_priority[str(result["intake"]["data"]["priority"])] += 1
            by_owner_team[str(result["routing"]["data"]["owner_team"])] += 1
            by_recommended_action[str(result["routing"]["data"]["recommended_action"])] += 1
            by_sla[str(result["routing"]["data"]["sla"])] += 1
            by_approval_status[str(row["approval_status"] or result["approval"]["status"])] += 1
            quality_scores.append(int(result["quality"]["data"]["quality_score"]))

        average_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0
        return {
            "total_tickets": len(rows),
            "by_priority": _ordered_counts(by_priority, ["critical", "high", "medium", "low"]),
            "by_owner_team": dict(sorted(by_owner_team.items())),
            "by_recommended_action": dict(sorted(by_recommended_action.items())),
            "by_sla": dict(sorted(by_sla.items())),
            "by_approval_status": _ordered_counts(
                by_approval_status,
                ["pending", "approved", "changes_requested", "escalated"],
            ),
            "average_quality_score": average_quality,
        }

    def _normalize_result(self, result: dict[str, Any]) -> dict[str, Any]:
        result.setdefault("approval", ApprovalState().to_dict())
        result.setdefault("ticket", {}).setdefault("metadata", {})
        return result

    def _apply_approval_to_triage(self, result: dict[str, Any], approval: dict[str, Any]) -> None:
        quality_data = result.get("quality", {}).get("data", {})
        routing_data = result.get("routing", {}).get("data", {})
        tags = set(routing_data.get("tags", []))

        quality_data["approved_for_send"] = approval["status"] == "approved"
        if approval["status"] == "approved":
            tags.add("draft-approved")
            routing_data["recommended_action"] = "send_draft"
        elif approval["status"] == "changes_requested":
            tags.discard("draft-approved")
            tags.add("needs-revision")
            routing_data["recommended_action"] = "revise_draft"
        elif approval["status"] == "escalated":
            tags.discard("draft-approved")
            tags.add("needs-human-review")
            routing_data["recommended_action"] = "human_review"
        else:
            tags.discard("draft-approved")
            routing_data["recommended_action"] = (
                "human_review" if "needs-human-review" in tags else "approval_required"
            )

        routing_data["tags"] = sorted(tags)

        for step in result.get("trace", []):
            if step.get("agent") == "Quality Agent":
                step.setdefault("data", {})["approved_for_send"] = quality_data["approved_for_send"]
            if step.get("agent") == "Routing Agent":
                step.setdefault("data", {})["tags"] = routing_data["tags"]
                step["data"]["recommended_action"] = routing_data["recommended_action"]


def _ordered_counts(counter: Counter[str], preferred_order: list[str]) -> dict[str, int]:
    ordered = {key: counter[key] for key in preferred_order if counter[key]}
    for key in sorted(counter):
        if key not in ordered:
            ordered[key] = counter[key]
    return ordered
