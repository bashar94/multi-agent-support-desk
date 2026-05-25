"""Shared domain models for tickets, agent decisions, and triage results."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Ticket:
    subject: str
    message: str
    customer_email: str = ""
    source: str = "manual"
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

        return cls(
            id=str(payload.get("id") or uuid4()),
            subject=subject,
            message=message,
            customer_email=str(payload.get("customer_email", "")).strip(),
            source=str(payload.get("source", "manual")).strip() or "manual",
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
class TriageResult:
    ticket: Ticket
    intake: AgentDecision
    knowledge: AgentDecision
    diagnostic: AgentDecision
    response: AgentDecision
    quality: AgentDecision
    routing: AgentDecision
    trace: list[AgentDecision]
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
            "created_at": self.created_at,
        }
