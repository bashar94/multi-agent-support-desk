"""SQLite persistence for tickets and agent run outputs."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

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

    def _execute(
        self,
        connection: sqlite3.Connection,
        statement: str,
        params: tuple[Any, ...] = (),
    ) -> sqlite3.Cursor:
        return connection.execute(statement, params)

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
            self._execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS reviewers (
                    email TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )
            self._execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS approval_audit_log (
                    id TEXT PRIMARY KEY,
                    ticket_id TEXT NOT NULL,
                    actor_email TEXT NOT NULL,
                    action TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """,
            )
            self._execute(
                connection,
                "CREATE INDEX IF NOT EXISTS idx_audit_ticket_id ON approval_audit_log(ticket_id)",
            )
            self._execute(
                connection,
                """
                CREATE TABLE IF NOT EXISTS oauth_installs (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    state TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    authorization_url TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    installed_by TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT '',
                    token_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
            )
            self._execute(
                connection,
                "CREATE INDEX IF NOT EXISTS idx_oauth_provider ON oauth_installs(provider)",
            )
            self._ensure_column(connection, "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(connection, "approval_status", "TEXT NOT NULL DEFAULT 'pending'")
            self._ensure_column(connection, "approval_reviewer", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "approval_note", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(connection, "approval_updated_at", "TEXT NOT NULL DEFAULT ''")

    def _ensure_column(self, connection: sqlite3.Connection, column: str, definition: str) -> None:
        columns = {row["name"] for row in self._execute(connection, "PRAGMA table_info(tickets)").fetchall()}
        if column not in columns:
            self._execute(connection, f"ALTER TABLE tickets ADD COLUMN {column} {definition}")

    def save_result(self, result: TriageResult) -> dict[str, Any]:
        payload = result.to_dict()
        ticket = result.ticket
        approval = payload["approval"]
        with self._connection() as connection:
            self._execute(
                connection,
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
            rows = self._execute(
                connection,
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
            row = self._execute(
                connection,
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
            row = self._execute(
                connection,
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
        actor: str = "",
    ) -> dict[str, Any] | None:
        result = self.get_result(ticket_id)
        if result is None:
            return None
        before = dict(result.get("approval", {}))
        actor_email = (reviewer or actor or "system").strip()

        approval = ApprovalState.from_payload(
            {
                "status": status,
                "reviewer": reviewer or actor_email,
                "note": note,
            }
        ).to_dict()
        result["approval"] = approval
        self._apply_approval_to_triage(result, approval)

        with self._connection() as connection:
            self._upsert_reviewer_in_connection(connection, actor_email, actor_email, "reviewer")
            self._execute(
                connection,
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
            self._record_audit_in_connection(
                connection,
                ticket_id=ticket_id,
                actor_email=actor_email,
                action=f"approval.{approval['status']}",
                before=before,
                after=approval,
                note=approval["note"],
            )
        return result

    def analytics(self) -> dict[str, Any]:
        with self._connection() as connection:
            rows = self._execute(connection, "SELECT result_json, approval_status FROM tickets").fetchall()

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

    def upsert_reviewer(
        self,
        email: str,
        display_name: str = "",
        role: str = "reviewer",
        active: bool = True,
    ) -> dict[str, Any]:
        normalized_email = _normalize_email(email)
        now = utc_now()
        with self._connection() as connection:
            self._execute(
                connection,
                """
                INSERT INTO reviewers (email, display_name, role, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    display_name = excluded.display_name,
                    role = excluded.role,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_email,
                    display_name.strip() or normalized_email,
                    role.strip() or "reviewer",
                    1 if active else 0,
                    now,
                    now,
                ),
            )
        return self.get_reviewer(normalized_email) or {}

    def get_reviewer(self, email: str) -> dict[str, Any] | None:
        normalized_email = _normalize_email(email)
        with self._connection() as connection:
            row = self._execute(
                connection,
                """
                SELECT email, display_name, role, active, created_at, updated_at
                FROM reviewers
                WHERE email = ?
                """,
                (normalized_email,),
            ).fetchone()
        return _reviewer_from_row(row) if row else None

    def list_reviewers(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = self._execute(
                connection,
                """
                SELECT email, display_name, role, active, created_at, updated_at
                FROM reviewers
                ORDER BY display_name, email
                """,
            ).fetchall()
        return [_reviewer_from_row(row) for row in rows]

    def audit_log(self, ticket_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        params: tuple[Any, ...]
        where = ""
        if ticket_id:
            where = "WHERE ticket_id = ?"
            params = (ticket_id, limit)
        else:
            params = (limit,)

        with self._connection() as connection:
            rows = self._execute(
                connection,
                f"""
                SELECT id, ticket_id, actor_email, action, before_json, after_json, note, created_at
                FROM approval_audit_log
                {where}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()

        return [
            {
                "id": row["id"],
                "ticket_id": row["ticket_id"],
                "actor_email": row["actor_email"],
                "action": row["action"],
                "before": json.loads(row["before_json"] or "{}"),
                "after": json.loads(row["after_json"] or "{}"),
                "note": row["note"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def begin_oauth_install(
        self,
        provider: str,
        state: str,
        authorization_url: str,
        redirect_uri: str,
        scopes: list[str],
        installed_by: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        install_id = str(uuid4())
        with self._connection() as connection:
            self._execute(
                connection,
                """
                INSERT INTO oauth_installs (
                    id,
                    provider,
                    state,
                    status,
                    scopes_json,
                    authorization_url,
                    redirect_uri,
                    installed_by,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    install_id,
                    provider,
                    state,
                    "pending",
                    json.dumps(scopes),
                    authorization_url,
                    redirect_uri,
                    installed_by,
                    json.dumps(metadata or {}),
                    now,
                    now,
                ),
            )
        return self.get_oauth_install(state) or {}

    def complete_oauth_install(
        self,
        state: str,
        code: str,
        metadata: dict[str, Any] | None = None,
        token: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        install = self.get_oauth_install(state)
        if install is None:
            return None

        merged_metadata = dict(install.get("metadata", {}))
        merged_metadata.update(metadata or {})
        with self._connection() as connection:
            self._execute(
                connection,
                """
                UPDATE oauth_installs
                SET status = ?, code = ?, token_json = ?, metadata_json = ?, updated_at = ?
                WHERE state = ?
                """,
                (
                    "connected",
                    code,
                    json.dumps(token or {}),
                    json.dumps(merged_metadata),
                    utc_now(),
                    state,
                ),
            )
        return self.get_oauth_install(state)

    def get_oauth_install(self, state: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = self._execute(
                connection,
                """
                SELECT
                    id,
                    provider,
                    state,
                    status,
                    scopes_json,
                    authorization_url,
                    redirect_uri,
                    installed_by,
                    code,
                    token_json,
                    metadata_json,
                    created_at,
                    updated_at
                FROM oauth_installs
                WHERE state = ?
                """,
                (state,),
            ).fetchone()
        return _oauth_install_from_row(row) if row else None

    def list_oauth_installs(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = self._execute(
                connection,
                """
                SELECT
                    id,
                    provider,
                    state,
                    status,
                    scopes_json,
                    authorization_url,
                    redirect_uri,
                    installed_by,
                    code,
                    token_json,
                    metadata_json,
                    created_at,
                    updated_at
                FROM oauth_installs
                ORDER BY updated_at DESC
                """,
            ).fetchall()
        return [_oauth_install_from_row(row) for row in rows]

    def _upsert_reviewer_in_connection(
        self,
        connection: sqlite3.Connection,
        email: str,
        display_name: str,
        role: str,
    ) -> None:
        normalized_email = _normalize_email(email)
        now = utc_now()
        self._execute(
            connection,
            """
            INSERT INTO reviewers (email, display_name, role, active, created_at, updated_at)
            VALUES (?, ?, ?, 1, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name = excluded.display_name,
                role = excluded.role,
                active = 1,
                updated_at = excluded.updated_at
            """,
            (
                normalized_email,
                display_name.strip() or normalized_email,
                role.strip() or "reviewer",
                now,
                now,
            ),
        )

    def _record_audit_in_connection(
        self,
        connection: sqlite3.Connection,
        ticket_id: str,
        actor_email: str,
        action: str,
        before: dict[str, Any],
        after: dict[str, Any],
        note: str,
    ) -> None:
        self._execute(
            connection,
            """
            INSERT INTO approval_audit_log (
                id,
                ticket_id,
                actor_email,
                action,
                before_json,
                after_json,
                note,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                ticket_id,
                _normalize_email(actor_email),
                action,
                json.dumps(before),
                json.dumps(after),
                note,
                utc_now(),
            ),
        )

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


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("reviewer email is required")
    return normalized


def _reviewer_from_row(row: Any) -> dict[str, Any]:
    return {
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "active": bool(row["active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _oauth_install_from_row(row: Any) -> dict[str, Any]:
    token = json.loads(row["token_json"] or "{}")
    return {
        "id": row["id"],
        "provider": row["provider"],
        "state": row["state"],
        "status": row["status"],
        "scopes": json.loads(row["scopes_json"] or "[]"),
        "authorization_url": row["authorization_url"],
        "redirect_uri": row["redirect_uri"],
        "installed_by": row["installed_by"],
        "has_code": bool(row["code"]),
        "has_token": bool(token),
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
