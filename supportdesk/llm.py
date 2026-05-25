"""Optional OpenAI-compatible LLM adapter."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class LLMClient(Protocol):
    def draft_reply(self, system_prompt: str, user_prompt: str) -> str:
        """Return a customer-facing draft reply."""


@dataclass(frozen=True)
class OpenAICompatibleClient:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4.1-mini"
    timeout_seconds: int = 25

    @classmethod
    def from_env(cls) -> "OpenAICompatibleClient | None":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", cls.base_url).strip().rstrip("/"),
            model=os.environ.get("OPENAI_MODEL", cls.model).strip(),
        )

    def draft_reply(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM provider returned HTTP {exc.code}: {body[:240]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM provider request failed: {exc.reason}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM provider returned no choices")

        message = choices[0].get("message", {})
        content = str(message.get("content", "")).strip()
        if not content:
            raise RuntimeError("LLM provider returned an empty message")
        return content
