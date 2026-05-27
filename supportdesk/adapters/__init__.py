"""Input adapters that normalize external support sources into tickets."""

from supportdesk.adapters.github_issues import ticket_from_github_issue_payload
from supportdesk.adapters.slack import ticket_from_slack_payload

__all__ = ["ticket_from_github_issue_payload", "ticket_from_slack_payload"]
