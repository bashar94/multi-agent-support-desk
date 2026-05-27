import unittest

from supportdesk.knowledge import KnowledgeBase
from supportdesk.models import KnowledgeArticle, Ticket
from supportdesk.orchestrator import SupportDeskOrchestrator


class AgentPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.knowledge_base = KnowledgeBase(
            [
                KnowledgeArticle(
                    id="kb-billing-refund",
                    title="Refund and duplicate charge handling",
                    category="billing",
                    content="Duplicate charges should be reviewed by Revenue Operations with invoice evidence.",
                    team="Revenue Operations",
                    keywords=["billing", "refund", "charged twice", "invoice", "payment"],
                ),
                KnowledgeArticle(
                    id="kb-login-reset",
                    title="Account access recovery",
                    category="account_access",
                    content="Password and MFA lockouts require account email and workspace confirmation.",
                    team="Support Operations",
                    keywords=["login", "password", "locked", "mfa", "account email"],
                ),
            ]
        )
        self.orchestrator = SupportDeskOrchestrator(self.knowledge_base)

    def test_billing_ticket_routes_to_revenue_operations(self) -> None:
        ticket = Ticket(
            subject="We were charged twice",
            message="I am frustrated because our card was charged twice and we need a refund.",
            customer_email="customer@example.com",
        )

        result = self.orchestrator.run(ticket)

        self.assertEqual(result.intake.data["category"], "billing")
        self.assertEqual(result.routing.data["owner_team"], "Revenue Operations")
        self.assertIn("needs-human-review", result.routing.data["tags"])
        self.assertTrue(result.knowledge.data["matches"])
        self.assertTrue(result.quality.data["quality_gate_passed"])
        self.assertFalse(result.quality.data["approved_for_send"])

    def test_account_access_ticket_requests_missing_context(self) -> None:
        ticket = Ticket(
            subject="Cannot login",
            message="My password reset is not working and I am blocked.",
            customer_email="customer@example.com",
        )

        result = self.orchestrator.run(ticket)

        self.assertEqual(result.intake.data["category"], "account_access")
        self.assertIn("organization or workspace name", result.diagnostic.data["missing_information"])
        self.assertIn("specialist team", result.response.data["draft"])


if __name__ == "__main__":
    unittest.main()
