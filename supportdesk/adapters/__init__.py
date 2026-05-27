"""Input adapters that normalize external support sources into tickets."""

from supportdesk.adapters.discord import ticket_from_discord_payload
from supportdesk.adapters.gmail import ticket_from_gmail_payload
from supportdesk.adapters.github_issues import ticket_from_github_issue_payload
from supportdesk.adapters.slack import ticket_from_slack_payload
from supportdesk.adapters.zendesk import ticket_from_zendesk_payload

__all__ = [
    "ticket_from_discord_payload",
    "ticket_from_github_issue_payload",
    "ticket_from_gmail_payload",
    "ticket_from_slack_payload",
    "ticket_from_zendesk_payload",
]
