"""Discord intake adapter for message and interaction payloads."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from supportdesk.models import Ticket


def ticket_from_discord_payload(payload: dict[str, Any]) -> Ticket:
    event = payload.get("d", payload)
    if not isinstance(event, dict):
        raise ValueError("Discord payload is required")

    if "content" in event:
        return _ticket_from_message(event, payload)
    if "data" in event:
        return _ticket_from_interaction(event, payload)
    raise ValueError("unsupported Discord payload")


def _ticket_from_message(event: dict[str, Any], payload: dict[str, Any]) -> Ticket:
    raw_content = str(event.get("content") or "").strip()
    if not raw_content:
        raise ValueError("Discord message content is required")

    author = event.get("author") if isinstance(event.get("author"), dict) else {}
    channel_id = str(event.get("channel_id") or payload.get("channel_id") or "")
    guild_id = str(event.get("guild_id") or payload.get("guild_id") or "")
    message_id = str(event.get("id") or payload.get("id") or "")
    author_name = _display_name(author)

    metadata = {
        "provider": "discord",
        "payload_type": "message",
        "message_id": message_id,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "author_id": author.get("id", ""),
        "author_username": author.get("username", ""),
        "timestamp": event.get("timestamp", ""),
    }

    return Ticket(
        id=f"discord-{_digest(message_id, channel_id, author.get('id', ''), raw_content)}",
        subject=_subject_from_text(raw_content),
        message=_clean_text(raw_content),
        customer_email=author_name,
        source=f"discord:{channel_id}" if channel_id else "discord",
        metadata=_clean_metadata(metadata),
    )


def _ticket_from_interaction(event: dict[str, Any], payload: dict[str, Any]) -> Ticket:
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    user = event.get("user")
    if not isinstance(user, dict):
        member = event.get("member") if isinstance(event.get("member"), dict) else {}
        user = member.get("user") if isinstance(member.get("user"), dict) else {}

    command_name = str(data.get("name") or payload.get("command") or "support").strip()
    option_lines = _option_lines(data.get("options", []))
    body = "\n".join(option_lines).strip() or command_name
    channel_id = str(event.get("channel_id") or payload.get("channel_id") or "")
    guild_id = str(event.get("guild_id") or payload.get("guild_id") or "")
    interaction_id = str(event.get("id") or payload.get("id") or "")

    metadata = {
        "provider": "discord",
        "payload_type": "interaction",
        "interaction_id": interaction_id,
        "command": command_name,
        "channel_id": channel_id,
        "guild_id": guild_id,
        "user_id": user.get("id", ""),
        "username": user.get("username", ""),
    }

    return Ticket(
        id=f"discord-{_digest(interaction_id, channel_id, user.get('id', ''), command_name, body)}",
        subject=_subject_from_text(body) if body != command_name else f"Discord /{command_name}",
        message=body,
        customer_email=_display_name(user),
        source=f"discord:{channel_id}" if channel_id else "discord",
        metadata=_clean_metadata(metadata),
    )


def _option_lines(options: object) -> list[str]:
    if not isinstance(options, list):
        return []

    lines = []
    for option in options:
        if not isinstance(option, dict):
            continue
        name = str(option.get("name") or "value")
        if isinstance(option.get("options"), list):
            child_lines = _option_lines(option["options"])
            lines.extend(child_lines)
            continue
        value = str(option.get("value") or "").strip()
        if value:
            lines.append(f"{name}: {value}")
    return lines


def _display_name(user: dict[str, Any]) -> str:
    username = str(user.get("global_name") or user.get("username") or "").strip()
    discriminator = str(user.get("discriminator") or "").strip()
    if username and discriminator and discriminator != "0":
        return f"{username}#{discriminator}"
    return username


def _subject_from_text(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) <= 90:
        return first_line
    return f"{first_line[:87].rstrip()}..."


def _clean_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.replace("\r", "\n").splitlines() if line.strip())


def _digest(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value not in ("", None, [], {})}
