"""Slack intake adapter for message events and slash commands."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from supportdesk.models import Ticket


def ticket_from_slack_payload(payload: dict[str, Any]) -> Ticket:
    if "event" in payload:
        return _ticket_from_event(payload)
    if "command" in payload or "trigger_id" in payload:
        return _ticket_from_slash_command(payload)
    raise ValueError("unsupported Slack payload")


def _ticket_from_event(payload: dict[str, Any]) -> Ticket:
    event = payload.get("event")
    if not isinstance(event, dict):
        raise ValueError("Slack event payload is required")

    raw_text = str(event.get("text", "")).strip()
    text = _clean_text(raw_text)
    if not text:
        raise ValueError("Slack message text is required")

    team_id = str(payload.get("team_id") or event.get("team") or "")
    channel_id = str(event.get("channel") or payload.get("channel_id") or "")
    user_id = str(event.get("user") or "")
    event_ts = str(event.get("ts") or payload.get("event_time") or "")
    profile = _nested_dict(payload, "authorizations", 0, default={})

    metadata = {
        "provider": "slack",
        "payload_type": "message_event",
        "team_id": team_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "event_ts": event_ts,
    }

    if profile:
        metadata["authorization"] = profile

    return Ticket(
        id=f"slack-{_digest(team_id, channel_id, event_ts, user_id, text)}",
        subject=_subject_from_text(raw_text),
        message=text,
        customer_email=_customer_from_slack(payload, event),
        source=f"slack:{channel_id}" if channel_id else "slack",
        metadata=_clean_metadata(metadata),
    )


def _ticket_from_slash_command(payload: dict[str, Any]) -> Ticket:
    raw_text = str(payload.get("text", "")).strip()
    text = _clean_text(raw_text)
    if not text:
        raise ValueError("Slack slash command text is required")

    team_id = str(payload.get("team_id") or "")
    channel_id = str(payload.get("channel_id") or "")
    channel_name = str(payload.get("channel_name") or "")
    user_id = str(payload.get("user_id") or "")
    user_name = str(payload.get("user_name") or "")
    trigger_id = str(payload.get("trigger_id") or "")

    metadata = {
        "provider": "slack",
        "payload_type": "slash_command",
        "command": str(payload.get("command") or ""),
        "team_id": team_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "user_id": user_id,
        "user_name": user_name,
        "trigger_id": trigger_id,
    }

    channel = channel_id or channel_name
    return Ticket(
        id=f"slack-{_digest(team_id, channel, user_id, trigger_id, text)}",
        subject=_subject_from_text(raw_text),
        message=text,
        customer_email=str(payload.get("user_email") or user_name or user_id),
        source=f"slack:{channel}" if channel else "slack",
        metadata=_clean_metadata(metadata),
    )


def _subject_from_text(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) <= 90:
        return first_line
    sentence = first_line.split(".", 1)[0].strip()
    if 12 <= len(sentence) <= 90:
        return sentence
    return f"{first_line[:87].rstrip()}..."


def _customer_from_slack(payload: dict[str, Any], event: dict[str, Any]) -> str:
    for candidate in (
        _nested_dict(event, "user_profile", "email"),
        _nested_dict(payload, "user", "profile", "email"),
        payload.get("user_email"),
        payload.get("user_name"),
        event.get("user"),
    ):
        if candidate:
            return str(candidate)
    return ""


def _clean_text(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split())


def _digest(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value not in ("", None, [], {})}


def _nested_dict(value: Any, *keys: object, default: Any = "") -> Any:
    current = value
    for key in keys:
        if isinstance(key, int) and isinstance(current, list) and len(current) > key:
            current = current[key]
            continue
        if isinstance(current, dict) and key in current:
            current = current[key]
            continue
        return default
    return current
