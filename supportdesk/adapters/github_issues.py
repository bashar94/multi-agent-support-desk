"""GitHub Issues intake adapter."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from supportdesk.models import Ticket


def ticket_from_github_issue_payload(payload: dict[str, Any]) -> Ticket:
    issue = payload.get("issue", payload)
    if not isinstance(issue, dict):
        raise ValueError("GitHub issue payload is required")

    title = str(issue.get("title", "")).strip()
    if not title:
        raise ValueError("GitHub issue title is required")

    repository = _repository_name(payload)
    number = issue.get("number", "")
    labels = _labels(issue.get("labels", []))
    reporter = issue.get("user") if isinstance(issue.get("user"), dict) else {}
    reporter_login = str(reporter.get("login") or "")
    issue_url = str(issue.get("html_url") or issue.get("url") or "")
    body = str(issue.get("body") or "No issue body was provided.").strip()
    message = _message(body, issue_url, labels)

    metadata = {
        "provider": "github",
        "payload_type": "issue",
        "repository": repository,
        "issue_number": number,
        "issue_url": issue_url,
        "labels": labels,
        "reporter_login": reporter_login,
        "reporter_id": reporter.get("id", ""),
        "state": issue.get("state", ""),
        "action": payload.get("action", ""),
    }

    return Ticket(
        id=f"github-issue-{_digest(repository, number, issue_url, title)}",
        subject=title,
        message=message,
        customer_email=reporter_login,
        source=f"github:{repository}" if repository else "github",
        metadata=_clean_metadata(metadata),
    )


def _repository_name(payload: dict[str, Any]) -> str:
    repository = payload.get("repository")
    if isinstance(repository, dict):
        return str(repository.get("full_name") or repository.get("name") or "")
    return str(payload.get("repository_full_name") or "")


def _labels(raw_labels: object) -> list[str]:
    if not isinstance(raw_labels, list):
        return []

    labels = []
    for item in raw_labels:
        if isinstance(item, dict) and item.get("name"):
            labels.append(str(item["name"]))
        elif isinstance(item, str):
            labels.append(item)
    return labels


def _message(body: str, issue_url: str, labels: list[str]) -> str:
    sections = [body]
    if labels:
        sections.append(f"Labels: {', '.join(labels)}")
    if issue_url:
        sections.append(f"Issue URL: {issue_url}")
    return "\n\n".join(section for section in sections if section)


def _digest(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value not in ("", None, [], {})}
