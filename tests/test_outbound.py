import os
import unittest
from unittest.mock import patch

from supportdesk.outbound import deliver_reply


class OutboundDeliveryTest(unittest.TestCase):
    def test_dry_run_delivery_is_default_safe_mode(self) -> None:
        delivery = deliver_reply(
            channel="email",
            recipient="customer@example.com",
            subject="Re: Login issue",
            body="Thanks for reaching out.",
            ticket_id="ticket-123",
            provider="dashboard",
            dry_run=True,
        )

        self.assertEqual(delivery["status"], "dry_run")
        self.assertEqual(delivery["channel"], "email")

    def test_send_mode_without_smtp_falls_back_to_outbox_dry_run(self) -> None:
        with patch.dict(os.environ, {"SUPPORT_DESK_REPLY_MODE": "send"}, clear=True):
            delivery = deliver_reply(
                channel="email",
                recipient="customer@example.com",
                subject="Re: Login issue",
                body="Thanks for reaching out.",
                ticket_id="ticket-123",
                provider="dashboard",
                dry_run=False,
            )

        self.assertEqual(delivery["status"], "dry_run")
        self.assertIn("SMTP", delivery["error"])


if __name__ == "__main__":
    unittest.main()
