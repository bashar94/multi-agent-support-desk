"""Outbound reply delivery helpers.

The default delivery mode is a safe dry run. Set SUPPORT_DESK_REPLY_MODE=send
and configure SMTP or a webhook to send replies outside the local outbox.
"""

from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib import request


def deliver_reply(
    *,
    channel: str,
    recipient: str,
    subject: str,
    body: str,
    ticket_id: str,
    provider: str,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    """Deliver a reply, or return a dry-run record when delivery is not configured."""

    normalized_channel = (channel or "email").strip().lower()
    should_dry_run = _should_dry_run(dry_run)
    if should_dry_run:
        return _delivery_result("dry_run", normalized_channel, provider, "dry run mode is enabled")

    if normalized_channel == "email":
        if _smtp_configured():
            return _send_email(recipient=recipient, subject=subject, body=body, ticket_id=ticket_id)
        return _delivery_result("dry_run", normalized_channel, provider, "SMTP is not configured")

    webhook_url = os.environ.get("SUPPORT_DESK_OUTBOUND_WEBHOOK_URL", "").strip()
    if webhook_url:
        return _send_webhook(
            webhook_url=webhook_url,
            channel=normalized_channel,
            recipient=recipient,
            subject=subject,
            body=body,
            ticket_id=ticket_id,
            provider=provider,
        )
    return _delivery_result("dry_run", normalized_channel, provider, "outbound webhook is not configured")


def _should_dry_run(dry_run: bool | None) -> bool:
    if dry_run is not None:
        return dry_run
    return os.environ.get("SUPPORT_DESK_REPLY_MODE", "dry_run").strip().lower() != "send"


def _smtp_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST", "").strip() and os.environ.get("SMTP_FROM", "").strip())


def _send_email(*, recipient: str, subject: str, body: str, ticket_id: str) -> dict[str, Any]:
    if not recipient:
        return _delivery_result("failed", "email", "smtp", "recipient is required")

    host = os.environ["SMTP_HOST"].strip()
    try:
        port = int(os.environ.get("SMTP_PORT", "587") or "587")
    except ValueError:
        return _delivery_result("failed", "email", "smtp", "SMTP_PORT must be a number")
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ["SMTP_FROM"].strip()
    use_tls = os.environ.get("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no", "off"}

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["X-SupportDesk-Ticket"] = ticket_id
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            if use_tls:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - depends on external SMTP service
        return _delivery_result("failed", "email", "smtp", str(exc))

    return _delivery_result("sent", "email", "smtp", "")


def _send_webhook(
    *,
    webhook_url: str,
    channel: str,
    recipient: str,
    subject: str,
    body: str,
    ticket_id: str,
    provider: str,
) -> dict[str, Any]:
    payload = {
        "ticket_id": ticket_id,
        "channel": channel,
        "provider": provider,
        "recipient": recipient,
        "subject": subject,
        "body": body,
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    webhook_request = request.Request(
        webhook_url,
        data=body_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(webhook_request, timeout=20) as response:  # noqa: S310
            status_code = int(response.status)
    except Exception as exc:  # pragma: no cover - depends on external webhook service
        return _delivery_result("failed", channel, "webhook", str(exc))

    if 200 <= status_code < 300:
        return _delivery_result("sent", channel, "webhook", "")
    return _delivery_result("failed", channel, "webhook", f"webhook returned HTTP {status_code}")


def _delivery_result(status: str, channel: str, provider: str, error: str) -> dict[str, Any]:
    return {
        "status": status,
        "channel": channel,
        "provider": provider,
        "error": error,
    }
