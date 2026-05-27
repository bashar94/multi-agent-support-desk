import tempfile
import unittest
from pathlib import Path

from supportdesk.knowledge import KnowledgeBase
from supportdesk.models import KnowledgeArticle, Ticket
from supportdesk.orchestrator import SupportDeskOrchestrator
from supportdesk.storage import TicketStore


class TicketStoreTest(unittest.TestCase):
    def test_saves_and_reads_triage_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TicketStore(Path(temp_dir) / "desk.sqlite3")
            orchestrator = SupportDeskOrchestrator(
                KnowledgeBase(
                    [
                        KnowledgeArticle(
                            id="kb-bug",
                            title="Bug report guide",
                            category="bug",
                            content="Collect reproduction steps.",
                            team="Product Engineering",
                            keywords=["bug", "error", "broken"],
                        )
                    ]
                )
            )
            result = orchestrator.run(Ticket(subject="Bug in import", message="CSV import is broken."))

            saved = store.save_result(result)
            loaded = store.get_result(result.ticket.id)
            tickets = store.list_tickets()

            self.assertEqual(saved["ticket"]["id"], result.ticket.id)
            self.assertEqual(loaded["ticket"]["id"], result.ticket.id)
            self.assertEqual(tickets[0]["owner_team"], "Product Engineering")
            self.assertEqual(tickets[0]["approval_status"], "pending")

    def test_updates_approval_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TicketStore(Path(temp_dir) / "desk.sqlite3")
            orchestrator = SupportDeskOrchestrator(KnowledgeBase([]))
            result = orchestrator.run(Ticket(subject="General question", message="Can you help me understand setup?"))
            store.save_result(result)

            updated = store.update_approval(
                result.ticket.id,
                status="approved",
                reviewer="lead@example.com",
                note="Ready to send.",
            )
            loaded = store.get_result(result.ticket.id)
            tickets = store.list_tickets()

            self.assertEqual(updated["approval"]["status"], "approved")
            self.assertTrue(updated["approval"]["send_ready"])
            self.assertTrue(updated["quality"]["data"]["approved_for_send"])
            self.assertEqual(updated["routing"]["data"]["recommended_action"], "send_draft")
            self.assertTrue(updated["trace"][4]["data"]["approved_for_send"])
            self.assertEqual(updated["trace"][5]["data"]["recommended_action"], "send_draft")
            self.assertEqual(loaded["approval"]["reviewer"], "lead@example.com")
            self.assertEqual(tickets[0]["approval_status"], "approved")

    def test_analytics_counts_routing_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TicketStore(Path(temp_dir) / "desk.sqlite3")
            orchestrator = SupportDeskOrchestrator(
                KnowledgeBase(
                    [
                        KnowledgeArticle(
                            id="kb-billing",
                            title="Billing guide",
                            category="billing",
                            content="Collect invoice evidence.",
                            team="Revenue Operations",
                            keywords=["billing", "refund", "invoice"],
                        )
                    ]
                )
            )
            result = orchestrator.run(Ticket(subject="Need refund", message="We were charged twice."))
            store.save_result(result)
            store.update_approval(result.ticket.id, status="escalated", reviewer="lead@example.com")

            analytics = store.analytics()

            self.assertEqual(analytics["total_tickets"], 1)
            self.assertEqual(analytics["by_priority"]["high"], 1)
            self.assertEqual(analytics["by_owner_team"]["Revenue Operations"], 1)
            self.assertEqual(analytics["by_approval_status"]["escalated"], 1)


if __name__ == "__main__":
    unittest.main()
