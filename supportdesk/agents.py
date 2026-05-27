"""Deterministic agents that collaborate to triage support tickets."""

from __future__ import annotations

import json
from typing import Any

from supportdesk.knowledge import KnowledgeBase
from supportdesk.llm import LLMClient
from supportdesk.models import AgentDecision, KnowledgeMatch, Ticket
from supportdesk.text import keyword_score, normalize, phrase_hits, tokenize


CATEGORY_RULES = {
    "outage": ["down", "outage", "incident", "unavailable", "service unavailable", "production is down"],
    "bug": ["bug", "broken", "error", "exception", "crash", "fails", "failed", "not working", "regression"],
    "billing": ["billing", "invoice", "charge", "charged", "refund", "payment", "subscription", "receipt"],
    "account_access": ["login", "password", "locked", "reset", "2fa", "mfa", "account access", "cannot sign in"],
    "integration": ["api", "webhook", "integration", "oauth", "token", "sync", "zapier", "slack"],
    "feature_request": ["feature", "request", "enhancement", "would like", "can you add", "roadmap"],
    "cancellation": ["cancel", "cancellation", "downgrade", "close account", "terminate"],
    "onboarding": ["setup", "onboarding", "configure", "getting started", "import", "migration"],
}

NEGATIVE_SENTIMENT = ["angry", "frustrated", "upset", "disappointed", "annoyed", "unacceptable", "terrible"]
POSITIVE_SENTIMENT = ["thanks", "great", "love", "appreciate", "helpful"]
CRITICAL_TERMS = ["security", "breach", "data loss", "production is down", "outage", "cannot access any"]
HIGH_TERMS = ["urgent", "asap", "blocked", "charged twice", "payment failed", "cannot login", "enterprise"]


def article_for(phrase: str) -> str:
    first = phrase.strip().lower()[:1]
    return "an" if first in {"a", "e", "i", "o", "u"} else "a"


class IntakeAgent:
    name = "Intake Agent"

    def run(self, ticket: Ticket) -> AgentDecision:
        text = f"{ticket.subject} {ticket.message}"
        category_scores: dict[str, float] = {}
        category_hits: dict[str, list[str]] = {}

        for category, keywords in CATEGORY_RULES.items():
            score, hits = keyword_score(text, keywords)
            category_scores[category] = score
            category_hits[category] = hits

        category = max(category_scores, key=category_scores.get)
        if category_scores[category] == 0:
            category = "general"

        critical_hits = phrase_hits(text, CRITICAL_TERMS)
        high_hits = phrase_hits(text, HIGH_TERMS)
        sentiment = self._sentiment(text)
        priority = self._priority(category, sentiment, critical_hits, high_hits)
        confidence = self._confidence(category_scores.get(category, 0), category)

        summary = f"Classified as {category.replace('_', ' ')} with {priority} priority."
        return AgentDecision(
            agent=self.name,
            summary=summary,
            confidence=confidence,
            data={
                "category": category,
                "priority": priority,
                "sentiment": sentiment,
                "matched_signals": category_hits.get(category, []),
                "critical_signals": critical_hits,
                "high_priority_signals": high_hits,
            },
        )

    def _sentiment(self, text: str) -> str:
        negative_hits = phrase_hits(text, NEGATIVE_SENTIMENT)
        positive_hits = phrase_hits(text, POSITIVE_SENTIMENT)
        if negative_hits and len(negative_hits) >= len(positive_hits):
            return "negative"
        if positive_hits:
            return "positive"
        return "neutral"

    def _priority(self, category: str, sentiment: str, critical_hits: list[str], high_hits: list[str]) -> str:
        if critical_hits or category == "outage":
            return "critical"
        if high_hits or category in {"billing", "account_access"}:
            return "high"
        if category in {"bug", "integration"} or sentiment == "negative":
            return "medium"
        return "low"

    def _confidence(self, score: float, category: str) -> float:
        if category == "general":
            return 0.35
        return round(min(0.95, 0.55 + score * 0.08), 2)


class KnowledgeAgent:
    name = "Knowledge Agent"

    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self.knowledge_base = knowledge_base

    def run(self, ticket: Ticket, intake: AgentDecision) -> AgentDecision:
        category = str(intake.data.get("category", ""))
        matches = self.knowledge_base.search(f"{ticket.subject} {ticket.message}", category=category)
        top_titles = [match.article.title for match in matches]
        summary = "Found relevant knowledge base context." if matches else "No strong knowledge base match found."
        confidence = min(0.95, 0.4 + (matches[0].score / 10 if matches else 0))

        return AgentDecision(
            agent=self.name,
            summary=summary,
            confidence=round(confidence, 2),
            data={
                "matches": [match.to_dict() for match in matches],
                "top_titles": top_titles,
                "grounding_status": "grounded" if matches else "needs_human_context",
            },
        )


class DiagnosticAgent:
    name = "Diagnostic Agent"

    REQUIRED_DETAILS = {
        "bug": ["steps to reproduce", "expected result", "actual result", "browser or app version"],
        "billing": ["invoice id or subscription email", "last four digits or receipt id"],
        "account_access": ["account email", "organization or workspace name"],
        "integration": ["integration name", "timestamp", "request id or webhook id"],
        "outage": ["affected workspace", "first observed time", "scope of impact"],
        "onboarding": ["target outcome", "current setup", "data source"],
    }

    def run(self, ticket: Ticket, intake: AgentDecision, knowledge: AgentDecision) -> AgentDecision:
        category = str(intake.data["category"])
        priority = str(intake.data["priority"])
        text = normalize(f"{ticket.subject} {ticket.message}")
        missing = self._missing_details(category, text)
        risk_flags = self._risk_flags(text, priority, category)
        matches = knowledge.data.get("matches", [])
        likely_cause = self._likely_cause(category, matches)
        escalation_required = priority in {"critical", "high"} or bool(risk_flags)

        if category == "feature_request":
            missing = ["business goal", "number of affected users", "current workaround"]

        summary = "Escalation recommended." if escalation_required else "Can be handled by first-line support."
        return AgentDecision(
            agent=self.name,
            summary=summary,
            confidence=0.82 if matches else 0.62,
            data={
                "escalation_required": escalation_required,
                "missing_information": missing,
                "risk_flags": risk_flags,
                "likely_cause": likely_cause,
                "customer_impact": self._customer_impact(priority, category),
            },
        )

    def _missing_details(self, category: str, text: str) -> list[str]:
        details = self.REQUIRED_DETAILS.get(category, ["desired outcome", "current behavior"])
        present_terms = set(tokenize(text))
        missing = []
        for detail in details:
            detail_terms = set(tokenize(detail))
            if not present_terms.intersection(detail_terms):
                missing.append(detail)
        return missing[:4]

    def _risk_flags(self, text: str, priority: str, category: str) -> list[str]:
        flags: list[str] = []
        if phrase_hits(text, ["security", "breach", "data leak", "privacy"]):
            flags.append("security_or_privacy")
        if phrase_hits(text, ["refund", "charged twice", "chargeback", "legal"]):
            flags.append("commercial_risk")
        if priority == "critical":
            flags.append("business_continuity")
        if category == "outage":
            flags.append("service_reliability")
        return sorted(set(flags))

    def _likely_cause(self, category: str, matches: list[dict[str, Any]]) -> str:
        if matches:
            title = matches[0]["article"]["title"]
            return f"Likely related to knowledge base article: {title}."
        if category == "general":
            return "Insufficient signal for a confident hypothesis."
        return f"Likely a {category.replace('_', ' ')} workflow issue."

    def _customer_impact(self, priority: str, category: str) -> str:
        if priority == "critical":
            return "Customer may be blocked from core business operations."
        if priority == "high":
            return "Customer likely needs same-day help to continue work."
        if category == "feature_request":
            return "Customer is asking for product improvement or workflow fit."
        return "Customer can likely continue with guidance or workaround."


class ResponseAgent:
    name = "Response Agent"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    def run(
        self,
        ticket: Ticket,
        intake: AgentDecision,
        knowledge: AgentDecision,
        diagnostic: AgentDecision,
    ) -> AgentDecision:
        category = str(intake.data["category"]).replace("_", " ")
        priority = str(intake.data["priority"])
        missing = diagnostic.data.get("missing_information", [])
        matches = [self._match_from_dict(item) for item in knowledge.data.get("matches", [])]
        escalation_required = bool(diagnostic.data.get("escalation_required"))
        draft = self._deterministic_draft(category, priority, missing, matches, escalation_required)
        generation_mode = "deterministic"
        llm_error = ""

        if self.llm_client is not None:
            try:
                draft = self.llm_client.draft_reply(
                    system_prompt=(
                        "You are a careful support specialist. Write a concise customer-facing reply. "
                        "Do not invent facts. Ask for missing information when needed."
                    ),
                    user_prompt=json.dumps(
                        {
                            "ticket": ticket.to_dict(),
                            "intake": intake.to_dict(),
                            "knowledge": knowledge.to_dict(),
                            "diagnostic": diagnostic.to_dict(),
                            "deterministic_fallback_draft": draft,
                        },
                        indent=2,
                    ),
                )
                generation_mode = "openai_compatible"
            except RuntimeError as exc:
                llm_error = str(exc)

        return AgentDecision(
            agent=self.name,
            summary="Drafted a grounded customer reply.",
            confidence=0.78 if matches else 0.58,
            data={
                "draft": draft,
                "uses_knowledge_base": bool(matches),
                "cited_articles": [match.article.title for match in matches],
                "generation_mode": generation_mode,
                "llm_error": llm_error,
            },
        )

    def _deterministic_draft(
        self,
        category: str,
        priority: str,
        missing: list[str],
        matches: list[KnowledgeMatch],
        escalation_required: bool,
    ) -> str:
        paragraphs = [
            "Hi there,",
            f"Thanks for reaching out. I reviewed your message and classified it as {article_for(category)} {category} request with {priority} priority.",
        ]

        if matches:
            primary = matches[0]
            paragraphs.append(
                f"The most relevant internal guidance is \"{primary.article.title}\". "
                f"Based on that guidance, the next best step is to verify the details below before making changes."
            )
        else:
            paragraphs.append(
                "I do not have a strong knowledge base match yet, so I would treat this carefully and avoid guessing."
            )

        if missing:
            formatted = "; ".join(missing)
            paragraphs.append(f"Could you send these details so we can investigate properly: {formatted}?")
        else:
            paragraphs.append("We have enough initial information to start investigating.")

        if escalation_required:
            paragraphs.append(
                "I am also routing this to the right specialist team because the impact or risk level is high enough for human follow-up."
            )
        else:
            paragraphs.append("I will keep this with the support team unless new information changes the priority.")

        paragraphs.append("Regards,\nSupport Team")
        return "\n\n".join(paragraphs)

    def _match_from_dict(self, item: dict[str, Any]) -> KnowledgeMatch:
        from supportdesk.models import KnowledgeArticle

        article = KnowledgeArticle(**item["article"])
        return KnowledgeMatch(article=article, score=float(item["score"]), matched_terms=list(item["matched_terms"]))


class QualityAgent:
    name = "Quality Agent"

    def run(
        self,
        intake: AgentDecision,
        knowledge: AgentDecision,
        diagnostic: AgentDecision,
        response: AgentDecision,
    ) -> AgentDecision:
        draft = str(response.data.get("draft", ""))
        checks = {
            "has_acknowledgement": "thanks" in draft.lower() or "reviewed" in draft.lower(),
            "has_next_step": "could you send" in draft.lower() or "routing" in draft.lower(),
            "mentions_priority": str(intake.data.get("priority", "")) in draft.lower(),
            "grounded_or_cautious": bool(knowledge.data.get("matches")) or "avoid guessing" in draft.lower(),
            "covers_escalation": not diagnostic.data.get("escalation_required") or "specialist team" in draft.lower(),
        }
        failed = [name for name, passed in checks.items() if not passed]
        quality_score = max(0, 100 - len(failed) * 18)
        hallucination_risk = "low" if checks["grounded_or_cautious"] else "medium"
        quality_gate_passed = quality_score >= 82 and hallucination_risk != "high"

        return AgentDecision(
            agent=self.name,
            summary=f"Quality score {quality_score}/100 with {hallucination_risk} hallucination risk.",
            confidence=0.86,
            data={
                "quality_score": quality_score,
                "failed_checks": failed,
                "checks": checks,
                "hallucination_risk": hallucination_risk,
                "quality_gate_passed": quality_gate_passed,
                "requires_human_approval": True,
                "approved_for_send": False,
            },
        )


class RoutingAgent:
    name = "Routing Agent"

    TEAM_BY_CATEGORY = {
        "outage": "Platform Reliability",
        "bug": "Product Engineering",
        "billing": "Revenue Operations",
        "account_access": "Support Operations",
        "integration": "Integrations Engineering",
        "feature_request": "Product Management",
        "cancellation": "Customer Success",
        "onboarding": "Customer Success",
        "general": "Support Operations",
    }

    SLA_BY_PRIORITY = {
        "critical": "1 hour",
        "high": "4 business hours",
        "medium": "1 business day",
        "low": "3 business days",
    }

    def run(self, intake: AgentDecision, diagnostic: AgentDecision, quality: AgentDecision) -> AgentDecision:
        category = str(intake.data["category"])
        priority = str(intake.data["priority"])
        owner_team = self.TEAM_BY_CATEGORY.get(category, "Support Operations")
        tags = [category, priority]

        if diagnostic.data.get("escalation_required"):
            tags.append("needs-human-review")
        if intake.data.get("sentiment") == "negative":
            tags.append("customer-friction")
        if diagnostic.data.get("missing_information"):
            tags.append("needs-more-info")
        if quality.data.get("quality_gate_passed"):
            tags.append("quality-ready")

        recommended_action = "human_review" if diagnostic.data.get("escalation_required") else "approval_required"

        return AgentDecision(
            agent=self.name,
            summary=f"Route to {owner_team} with {self.SLA_BY_PRIORITY[priority]} SLA.",
            confidence=0.9,
            data={
                "owner_team": owner_team,
                "sla": self.SLA_BY_PRIORITY[priority],
                "tags": sorted(set(tags)),
                "recommended_action": recommended_action,
            },
        )
