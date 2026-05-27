"""OAuth installation helpers for provider adapters."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    authorization_url: str
    client_id_env: str
    default_scopes: list[str]
    extra_params: dict[str, str] | None = None


PROVIDERS = {
    "gmail": OAuthProvider(
        name="gmail",
        authorization_url="https://accounts.google.com/o/oauth2/v2/auth",
        client_id_env="GMAIL_CLIENT_ID",
        default_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
        ],
        extra_params={"access_type": "offline", "prompt": "consent"},
    ),
    "slack": OAuthProvider(
        name="slack",
        authorization_url="https://slack.com/oauth/v2/authorize",
        client_id_env="SLACK_CLIENT_ID",
        default_scopes=["channels:history", "chat:write", "commands"],
    ),
    "zendesk": OAuthProvider(
        name="zendesk",
        authorization_url="",
        client_id_env="ZENDESK_CLIENT_ID",
        default_scopes=["read", "write"],
    ),
    "github": OAuthProvider(
        name="github",
        authorization_url="https://github.com/login/oauth/authorize",
        client_id_env="GITHUB_CLIENT_ID",
        default_scopes=["repo", "read:user"],
    ),
    "discord": OAuthProvider(
        name="discord",
        authorization_url="https://discord.com/oauth2/authorize",
        client_id_env="DISCORD_CLIENT_ID",
        default_scopes=["identify", "bot", "applications.commands"],
        extra_params={"permissions": "0"},
    ),
}


def list_oauth_providers() -> list[dict[str, Any]]:
    return [
        {
            "provider": provider.name,
            "client_id_env": provider.client_id_env,
            "configured": bool(os.environ.get(provider.client_id_env, "").strip()),
            "default_scopes": provider.default_scopes,
        }
        for provider in PROVIDERS.values()
    ]


def begin_oauth_install(
    provider_name: str,
    redirect_uri: str,
    scopes: list[str] | None = None,
    extra_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    provider = _provider(provider_name)
    client_id = os.environ.get(provider.client_id_env, "").strip()
    if not client_id:
        raise ValueError(f"{provider.client_id_env} is required to start {provider.name} OAuth")

    state = secrets.token_urlsafe(24)
    selected_scopes = scopes or provider.default_scopes
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(selected_scopes),
        "state": state,
    }
    params.update(provider.extra_params or {})
    params.update(extra_params or {})
    authorization_url = f"{_authorization_url(provider)}?{urlencode(params)}"

    return {
        "provider": provider.name,
        "state": state,
        "scopes": selected_scopes,
        "authorization_url": authorization_url,
        "redirect_uri": redirect_uri,
    }


def _provider(provider_name: str) -> OAuthProvider:
    key = provider_name.strip().lower()
    if key not in PROVIDERS:
        allowed = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"OAuth provider must be one of: {allowed}")
    return PROVIDERS[key]


def _authorization_url(provider: OAuthProvider) -> str:
    if provider.name == "zendesk":
        explicit = os.environ.get("ZENDESK_AUTHORIZE_URL", "").strip()
        if explicit:
            return explicit
        subdomain = os.environ.get("ZENDESK_SUBDOMAIN", "").strip()
        if subdomain:
            return f"https://{subdomain}.zendesk.com/oauth/authorizations/new"
        raise ValueError("ZENDESK_SUBDOMAIN or ZENDESK_AUTHORIZE_URL is required for Zendesk OAuth")
    return provider.authorization_url
