"""Gmail intake adapter for Gmail API message payloads."""

from __future__ import annotations

import base64
from email.utils import parseaddr
from hashlib import sha256
from typing import Any

from supportdesk.models import Ticket


def ticket_from_gmail_payload(payload: dict[str, Any]) -> Ticket:
    message = payload.get("message", payload)
    if not isinstance(message, dict):
        raise ValueError("Gmail message payload is required")

    headers = _headers(message)
    subject = _first(
        headers.get("subject", ""),
        payload.get("subject", ""),
        message.get("subject", ""),
        "Gmail support request",
    )
    sender_name, sender_email = parseaddr(_first(headers.get("from", ""), payload.get("from", "")))
    message_id = str(message.get("id") or payload.get("message_id") or payload.get("email_id") or "")
    thread_id = str(message.get("threadId") or message.get("thread_id") or payload.get("thread_id") or "")
    body = _body_text(message) or str(message.get("snippet") or payload.get("snippet") or subject).strip()
    if not body:
        raise ValueError("Gmail message body or snippet is required")

    metadata = {
        "provider": "gmail",
        "payload_type": "message",
        "message_id": message_id,
        "thread_id": thread_id,
        "history_id": message.get("historyId") or message.get("history_id") or payload.get("history_id"),
        "label_ids": message.get("labelIds") or message.get("label_ids") or payload.get("label_ids") or [],
        "sender_name": sender_name,
        "sender_email": sender_email,
        "internal_date": message.get("internalDate") or message.get("internal_date"),
    }

    return Ticket(
        id=f"gmail-{_digest(message_id, thread_id, sender_email, subject, body)}",
        subject=str(subject).strip(),
        message=_clean_text(body),
        customer_email=sender_email or sender_name,
        source=f"gmail:{sender_email}" if sender_email else "gmail",
        metadata=_clean_metadata(metadata),
    )


def _headers(message: dict[str, Any]) -> dict[str, str]:
    raw_headers = message.get("headers")
    if raw_headers is None and isinstance(message.get("payload"), dict):
        raw_headers = message["payload"].get("headers")

    headers: dict[str, str] = {}
    if isinstance(raw_headers, dict):
        return {str(key).lower(): str(value) for key, value in raw_headers.items()}
    if isinstance(raw_headers, list):
        for item in raw_headers:
            if isinstance(item, dict) and item.get("name"):
                headers[str(item["name"]).lower()] = str(item.get("value", ""))
    return headers


def _body_text(message: dict[str, Any]) -> str:
    for candidate in (message.get("body"), message.get("text"), message.get("plain_text")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    payload = message.get("payload")
    if isinstance(payload, dict):
        return _body_from_part(payload)
    return ""


def _body_from_part(part: dict[str, Any]) -> str:
    mime_type = str(part.get("mimeType") or part.get("mime_type") or "")
    body = part.get("body") if isinstance(part.get("body"), dict) else {}
    data = body.get("data") if isinstance(body, dict) else ""

    if data and (mime_type.startswith("text/plain") or not part.get("parts")):
        decoded = _decode_gmail_data(str(data))
        if decoded.strip():
            return decoded.strip()

    parts = part.get("parts")
    if isinstance(parts, list):
        fallback = ""
        for child in parts:
            if not isinstance(child, dict):
                continue
            child_text = _body_from_part(child)
            if str(child.get("mimeType", "")).startswith("text/plain") and child_text:
                return child_text
            fallback = fallback or child_text
        return fallback
    return ""


def _decode_gmail_data(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", errors="replace")
    except (ValueError, UnicodeEncodeError):
        return ""


def _first(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.replace("\r", "\n").splitlines() if line.strip())


def _digest(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value not in ("", None, [], {})}
