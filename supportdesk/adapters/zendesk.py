"""Zendesk intake adapter for ticket webhook payloads."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from supportdesk.models import Ticket


def ticket_from_zendesk_payload(payload: dict[str, Any]) -> Ticket:
    ticket = payload.get("ticket", payload)
    if not isinstance(ticket, dict):
        raise ValueError("Zendesk ticket payload is required")

    ticket_id = str(ticket.get("id") or ticket.get("ticket_id") or payload.get("ticket_id") or "")
    subject = str(ticket.get("subject") or payload.get("subject") or "").strip()
    if not subject:
        raise ValueError("Zendesk ticket subject is required")

    requester = ticket.get("requester") if isinstance(ticket.get("requester"), dict) else {}
    via = ticket.get("via") if isinstance(ticket.get("via"), dict) else {}
    requester_email = str(
        requester.get("email")
        or ticket.get("requester_email")
        or payload.get("requester_email")
        or requester.get("name")
        or ""
    ).strip()
    body = _body(ticket, payload)
    tags = _strings(ticket.get("tags") or payload.get("tags") or [])

    metadata = {
        "provider": "zendesk",
        "payload_type": "ticket",
        "ticket_id": ticket_id,
        "ticket_url": ticket.get("url") or ticket.get("html_url") or payload.get("ticket_url"),
        "priority": ticket.get("priority") or payload.get("priority"),
        "status": ticket.get("status") or payload.get("status"),
        "tags": tags,
        "requester_name": requester.get("name", ""),
        "requester_email": requester_email,
        "via_channel": via.get("channel", ""),
        "brand_id": ticket.get("brand_id", ""),
        "group_id": ticket.get("group_id", ""),
    }

    return Ticket(
        id=f"zendesk-{_digest(ticket_id, requester_email, subject, body)}",
        subject=subject,
        message=body,
        customer_email=requester_email,
        source=f"zendesk:{ticket_id}" if ticket_id else "zendesk",
        metadata=_clean_metadata(metadata),
    )


def _body(ticket: dict[str, Any], payload: dict[str, Any]) -> str:
    candidates = [
        ticket.get("description"),
        ticket.get("latest_comment"),
        ticket.get("comment"),
        payload.get("description"),
        payload.get("latest_comment"),
        payload.get("comment"),
    ]

    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("body", "plain_body", "value"):
                value = str(candidate.get(key) or "").strip()
                if value:
                    return value
        value = str(candidate or "").strip()
        if value:
            return value
    raise ValueError("Zendesk ticket description or comment is required")


def _strings(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _digest(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value not in ("", None, [], {})}
