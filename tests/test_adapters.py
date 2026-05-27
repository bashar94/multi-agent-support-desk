import json
import unittest
from pathlib import Path

from supportdesk.adapters import (
    ticket_from_discord_payload,
    ticket_from_github_issue_payload,
    ticket_from_gmail_payload,
    ticket_from_slack_payload,
    ticket_from_zendesk_payload,
)


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


class GmailAdapterTest(unittest.TestCase):
    def test_gmail_message_becomes_ticket(self) -> None:
        ticket = ticket_from_gmail_payload(load_fixture("gmail_message.json"))

        self.assertEqual(ticket.subject, "Cannot login after enabling MFA")
        self.assertEqual(ticket.source, "gmail:ops@example.com")
        self.assertEqual(ticket.customer_email, "ops@example.com")
        self.assertIn("password reset", ticket.message)
        self.assertEqual(ticket.metadata["thread_id"], "18f8d7c0a123")
        self.assertEqual(ticket.metadata["label_ids"], ["INBOX", "IMPORTANT"])


class ZendeskAdapterTest(unittest.TestCase):
    def test_zendesk_ticket_becomes_ticket(self) -> None:
        ticket = ticket_from_zendesk_payload(load_fixture("zendesk_ticket.json"))

        self.assertEqual(ticket.subject, "Refund needed for duplicate charge")
        self.assertEqual(ticket.source, "zendesk:9812")
        self.assertEqual(ticket.customer_email, "finance@example.com")
        self.assertIn("charged twice", ticket.message)
        self.assertEqual(ticket.metadata["tags"], ["billing", "refund"])
        self.assertEqual(ticket.metadata["via_channel"], "web")


class DiscordAdapterTest(unittest.TestCase):
    def test_discord_message_becomes_ticket(self) -> None:
        ticket = ticket_from_discord_payload(load_fixture("discord_message.json"))

        self.assertEqual(ticket.subject, "Webhook delivery failing")
        self.assertEqual(ticket.source, "discord:987654321")
        self.assertEqual(ticket.customer_email, "devlead")
        self.assertIn("401 errors", ticket.message)
        self.assertEqual(ticket.metadata["guild_id"], "123456789")
        self.assertEqual(ticket.metadata["payload_type"], "message")


if __name__ == "__main__":
    unittest.main()
