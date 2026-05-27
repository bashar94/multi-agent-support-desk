import json
import unittest
from pathlib import Path

from supportdesk.adapters import ticket_from_github_issue_payload, ticket_from_slack_payload


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class SlackAdapterTest(unittest.TestCase):
    def test_message_event_becomes_ticket(self) -> None:
        ticket = ticket_from_slack_payload(load_fixture("slack_message_event.json"))

        self.assertEqual(ticket.subject, "Cannot login after enabling MFA")
        self.assertEqual(ticket.source, "slack:C456")
        self.assertEqual(ticket.customer_email, "U789")
        self.assertEqual(ticket.metadata["provider"], "slack")
        self.assertEqual(ticket.metadata["payload_type"], "message_event")

    def test_slash_command_becomes_ticket(self) -> None:
        ticket = ticket_from_slack_payload(load_fixture("slack_slash_command.json"))

        self.assertEqual(ticket.subject, "Webhook delivery failing")
        self.assertEqual(ticket.source, "slack:C456")
        self.assertEqual(ticket.customer_email, "alex")
        self.assertEqual(ticket.metadata["command"], "/support")


class GitHubIssueAdapterTest(unittest.TestCase):
    def test_issue_payload_becomes_ticket_with_metadata(self) -> None:
        ticket = ticket_from_github_issue_payload(load_fixture("github_issue_opened.json"))

        self.assertEqual(ticket.subject, "CSV import crashes with large files")
        self.assertEqual(ticket.source, "github:example/widget-api")
        self.assertEqual(ticket.customer_email, "octo-customer")
        self.assertIn("https://github.com/example/widget-api/issues/42", ticket.message)
        self.assertEqual(ticket.metadata["issue_number"], 42)
        self.assertEqual(ticket.metadata["labels"], ["bug", "import"])


if __name__ == "__main__":
    unittest.main()
