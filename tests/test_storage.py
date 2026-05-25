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


if __name__ == "__main__":
    unittest.main()
