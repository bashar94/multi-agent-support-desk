"""Shared domain models for tickets, agent decisions, and triage results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

VALID_APPROVAL_STATUSES = {"pending", "approved", "changes_requested", "escalated"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Ticket:
    subject: str
    message: str
    customer_email: str = ""
    source: str = "manual"
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Ticket":
        subject = str(payload.get("subject", "")).strip()
        message = str(payload.get("message", "")).strip()
        if not subject:
            raise ValueError("subject is required")
        if not message:
            raise ValueError("message is required")

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        return cls(
            id=str(payload.get("id") or uuid4()),
            subject=subject,
            message=message,
            customer_email=str(payload.get("customer_email", "")).strip(),
            source=str(payload.get("source", "manual")).strip() or "manual",
            metadata=metadata,
            created_at=str(payload.get("created_at") or utc_now()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeArticle:
    id: str
    title: str
    category: str
    content: str
    team: str
    keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeMatch:
    article: KnowledgeArticle
    score: float
    matched_terms: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "matched_terms": self.matched_terms,
            "article": self.article.to_dict(),
        }


@dataclass(frozen=True)
class AgentDecision:
    agent: str
    summary: str
    confidence: float
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ApprovalState:
    status: str = "pending"
    reviewer: str = ""
    note: str = ""
    send_ready: bool = False
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ApprovalState":
        status = str(payload.get("status", "pending")).strip().lower()
        if status not in VALID_APPROVAL_STATUSES:
            allowed = ", ".join(sorted(VALID_APPROVAL_STATUSES))
            raise ValueError(f"approval status must be one of: {allowed}")

        return cls(
            status=status,
            reviewer=str(payload.get("reviewer", "")).strip(),
            note=str(payload.get("note", "")).strip(),
            send_ready=status == "approved",
            updated_at=str(payload.get("updated_at") or utc_now()),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TriageResult:
    ticket: Ticket
    intake: AgentDecision
    knowledge: AgentDecision
    diagnostic: AgentDecision
    response: AgentDecision
    quality: AgentDecision
    routing: AgentDecision
    trace: list[AgentDecision]
    approval: ApprovalState = field(default_factory=ApprovalState)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket.to_dict(),
            "intake": self.intake.to_dict(),
            "knowledge": self.knowledge.to_dict(),
            "diagnostic": self.diagnostic.to_dict(),
            "response": self.response.to_dict(),
            "quality": self.quality.to_dict(),
            "routing": self.routing.to_dict(),
            "trace": [step.to_dict() for step in self.trace],
            "approval": self.approval.to_dict(),
            "created_at": self.created_at,
        }
