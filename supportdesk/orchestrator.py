"""Pipeline orchestration for the support desk agents."""

from __future__ import annotations

from supportdesk.agents import (
    DiagnosticAgent,
    IntakeAgent,
    KnowledgeAgent,
    QualityAgent,
    ResponseAgent,
    RoutingAgent,
)
from supportdesk.knowledge import KnowledgeBase
from supportdesk.models import Ticket, TriageResult


class SupportDeskOrchestrator:
    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self.intake_agent = IntakeAgent()
        self.knowledge_agent = KnowledgeAgent(knowledge_base)
        self.diagnostic_agent = DiagnosticAgent()
        self.response_agent = ResponseAgent()
        self.quality_agent = QualityAgent()
        self.routing_agent = RoutingAgent()

    def run(self, ticket: Ticket) -> TriageResult:
        intake = self.intake_agent.run(ticket)
        knowledge = self.knowledge_agent.run(ticket, intake)
        diagnostic = self.diagnostic_agent.run(ticket, intake, knowledge)
        response = self.response_agent.run(ticket, intake, knowledge, diagnostic)
        quality = self.quality_agent.run(intake, knowledge, diagnostic, response)
        routing = self.routing_agent.run(intake, diagnostic, quality)
        trace = [intake, knowledge, diagnostic, response, quality, routing]

        return TriageResult(
            ticket=ticket,
            intake=intake,
            knowledge=knowledge,
            diagnostic=diagnostic,
            response=response,
            quality=quality,
            routing=routing,
            trace=trace,
        )
