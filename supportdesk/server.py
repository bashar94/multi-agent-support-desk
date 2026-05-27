"""Local HTTP server for the Multi-Agent Support Desk."""

from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from supportdesk.adapters import (
    ticket_from_discord_payload,
    ticket_from_github_issue_payload,
    ticket_from_gmail_payload,
    ticket_from_slack_payload,
    ticket_from_zendesk_payload,
)
from supportdesk.database import build_ticket_store
from supportdesk.defaults import (
    DEFAULT_DB_PATH,
    DEFAULT_HOST,
    DEFAULT_KNOWLEDGE_BASE,
    DEFAULT_PORT,
    DEFAULT_SAMPLE_TICKETS,
    FRONTEND_DIR,
)
from supportdesk.knowledge import KnowledgeBase
from supportdesk.llm import OpenAICompatibleClient
from supportdesk.models import Ticket
from supportdesk.oauth import begin_oauth_install, list_oauth_providers
from supportdesk.orchestrator import SupportDeskOrchestrator


class SupportDeskHandler(BaseHTTPRequestHandler):
    orchestrator: SupportDeskOrchestrator
    store: Any
    knowledge_base: KnowledgeBase
    sample_tickets_path: Path
    static_dir: Path

    server_version = "MultiAgentSupportDesk/0.1"

    def do_OPTIONS(self) -> None:
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/api/health":
                self._send_json({"status": "ok", "service": "multi-agent-support-desk"})
                return

            if path == "/api/knowledge":
                self._send_json({"articles": [article.to_dict() for article in self.knowledge_base.articles]})
                return

            if path == "/api/sample-tickets":
                self._send_json({"tickets": self._load_sample_tickets()})
                return

            if path == "/api/tickets":
                limit = int(query.get("limit", ["50"])[0])
                self._send_json({"tickets": self.store.list_tickets(limit=limit)})
                return

            if path == "/api/analytics":
                self._send_json({"analytics": self.store.analytics()})
                return

            if path == "/api/oauth/providers":
                self._send_json({"providers": list_oauth_providers()})
                return

            if path == "/api/oauth/installs":
                self._send_json({"installs": self.store.list_oauth_installs()})
                return

            if path == "/api/reviewers":
                self._send_json({"reviewers": self.store.list_reviewers()})
                return

            if path == "/api/audit-log":
                limit = int(query.get("limit", ["100"])[0])
                ticket_id = str(query.get("ticket_id", [""])[0])
                self._send_json({"events": self.store.audit_log(ticket_id=ticket_id, limit=limit)})
                return

            if path == "/api/outbox":
                limit = int(query.get("limit", ["50"])[0])
                ticket_id = str(query.get("ticket_id", [""])[0])
                self._send_json({"outbox": self.store.list_outbox(ticket_id=ticket_id, limit=limit)})
                return

            if path.startswith("/api/oauth/") and path.endswith("/callback"):
                provider = path.removeprefix("/api/oauth/").removesuffix("/callback").strip("/")
                code = str(query.get("code", [""])[0])
                state = str(query.get("state", [""])[0])
                if not code or not state:
                    self._send_json({"error": "code and state are required"}, HTTPStatus.BAD_REQUEST)
                    return
                install = self.store.complete_oauth_install(
                    state,
                    code,
                    metadata={"provider": provider, "callback_method": "GET"},
                )
                if install is None:
                    self._send_json({"error": "OAuth install state not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"install": install})
                return

            if path.startswith("/api/tickets/"):
                ticket_id = path.removeprefix("/api/tickets/").strip("/")
                result = self.store.get_result(ticket_id)
                if result is None:
                    self._send_json({"error": "ticket not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(result)
                return

            self._serve_static(path)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/tickets/analyze":
                payload = self._read_payload()
                ticket = Ticket.from_payload(payload)
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result), HTTPStatus.CREATED)
                return

            if path.startswith("/api/oauth/") and path.endswith("/begin"):
                provider = path.removeprefix("/api/oauth/").removesuffix("/begin").strip("/")
                payload = self._read_payload()
                redirect_uri = str(payload.get("redirect_uri") or self._default_redirect_uri(provider))
                scopes = payload.get("scopes")
                selected_scopes = [str(scope) for scope in scopes] if isinstance(scopes, list) else None
                extra_params = payload.get("extra_params")
                if not isinstance(extra_params, dict):
                    extra_params = {}
                flow = begin_oauth_install(provider, redirect_uri, selected_scopes, extra_params)
                install = self.store.begin_oauth_install(
                    provider=flow["provider"],
                    state=flow["state"],
                    authorization_url=flow["authorization_url"],
                    redirect_uri=flow["redirect_uri"],
                    scopes=flow["scopes"],
                    installed_by=str(payload.get("installed_by", "")),
                    metadata={"source": "api"},
                )
                self._send_json({"install": install}, HTTPStatus.CREATED)
                return

            if path.startswith("/api/oauth/") and path.endswith("/callback"):
                provider = path.removeprefix("/api/oauth/").removesuffix("/callback").strip("/")
                payload = self._read_payload()
                code = str(payload.get("code", ""))
                state = str(payload.get("state", ""))
                if not code or not state:
                    self._send_json({"error": "code and state are required"}, HTTPStatus.BAD_REQUEST)
                    return
                install = self.store.complete_oauth_install(
                    state,
                    code,
                    metadata={"provider": provider, "callback_method": "POST"},
                )
                if install is None:
                    self._send_json({"error": "OAuth install state not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"install": install})
                return

            if path == "/api/reviewers":
                payload = self._read_payload()
                reviewer = self.store.upsert_reviewer(
                    email=str(payload.get("email", "")),
                    display_name=str(payload.get("display_name", "")),
                    role=str(payload.get("role", "reviewer")),
                    active=bool(payload.get("active", True)),
                )
                self._send_json({"reviewer": reviewer}, HTTPStatus.CREATED)
                return

            if path == "/api/integrations/slack":
                payload = self._read_payload()
                if payload.get("type") == "url_verification":
                    self._send_json({"challenge": payload.get("challenge", "")})
                    return
                ticket = ticket_from_slack_payload(payload)
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result), HTTPStatus.CREATED)
                return

            if path == "/api/integrations/github-issues":
                payload = self._read_payload()
                ticket = ticket_from_github_issue_payload(payload)
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result), HTTPStatus.CREATED)
                return

            if path == "/api/integrations/gmail":
                payload = self._read_payload()
                ticket = ticket_from_gmail_payload(payload)
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result), HTTPStatus.CREATED)
                return

            if path == "/api/integrations/zendesk":
                payload = self._read_payload()
                ticket = ticket_from_zendesk_payload(payload)
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result), HTTPStatus.CREATED)
                return

            if path == "/api/integrations/discord":
                payload = self._read_payload()
                ticket = ticket_from_discord_payload(payload)
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result), HTTPStatus.CREATED)
                return

            if path.startswith("/api/tickets/") and path.endswith("/reanalyze"):
                ticket_id = path.removeprefix("/api/tickets/").removesuffix("/reanalyze").strip("/")
                ticket = self.store.get_ticket(ticket_id)
                if ticket is None:
                    self._send_json({"error": "ticket not found"}, HTTPStatus.NOT_FOUND)
                    return
                result = self.orchestrator.run(ticket)
                self._send_json(self.store.save_result(result))
                return

            if path.startswith("/api/tickets/") and path.endswith("/send-reply"):
                ticket_id = path.removeprefix("/api/tickets/").removesuffix("/send-reply").strip("/")
                payload = self._read_payload()
                try:
                    outbox_item = self.store.send_reply(
                        ticket_id,
                        channel=str(payload.get("channel", "")),
                        sender=str(payload.get("sender", "")),
                        dry_run=_optional_bool(payload.get("dry_run")),
                    )
                except ValueError as exc:
                    status = HTTPStatus.CONFLICT if "approved" in str(exc) else HTTPStatus.BAD_REQUEST
                    self._send_json({"error": str(exc)}, status)
                    return
                if outbox_item is None:
                    self._send_json({"error": "ticket not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json({"outbox": outbox_item, "ticket": self.store.get_result(ticket_id)})
                return

            if path.startswith("/api/tickets/") and path.endswith("/status"):
                ticket_id = path.removeprefix("/api/tickets/").removesuffix("/status").strip("/")
                payload = self._read_payload()
                result = self.store.update_ticket_status(
                    ticket_id,
                    status=str(payload.get("status", "")),
                    actor=str(payload.get("actor", "")),
                    note=str(payload.get("note", "")),
                )
                if result is None:
                    self._send_json({"error": "ticket not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(result)
                return

            if path.startswith("/api/tickets/") and path.endswith("/approval"):
                ticket_id = path.removeprefix("/api/tickets/").removesuffix("/approval").strip("/")
                payload = self._read_payload()
                result = self.store.update_approval(
                    ticket_id,
                    status=str(payload.get("status", "")),
                    reviewer=str(payload.get("reviewer", "")),
                    note=str(payload.get("note", "")),
                    actor=str(payload.get("actor", "")),
                )
                if result is None:
                    self._send_json({"error": "ticket not found"}, HTTPStatus.NOT_FOUND)
                    return
                self._send_json(result)
                return

            self._send_json({"error": "route not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _load_sample_tickets(self) -> list[dict[str, Any]]:
        with self.sample_tickets_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type == "application/x-www-form-urlencoded":
            parsed = parse_qs(raw, keep_blank_values=True)
            return {key: values[-1] if len(values) == 1 else values for key, values in parsed.items()}
        return json.loads(raw)

    def _default_redirect_uri(self, provider: str) -> str:
        scheme = self.headers.get("X-Forwarded-Proto", "http").split(",", 1)[0]
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host", "")
        return f"{scheme}://{host}/api/oauth/{provider}/callback"

    def _serve_static(self, path: str) -> None:
        requested = "index.html" if path in {"", "/"} else path.lstrip("/")
        target = (self.static_dir / requested).resolve()

        if not target.is_relative_to(self.static_dir.resolve()) or not target.exists() or target.is_dir():
            self._send_json({"error": "route not found"}, HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self._cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.log_date_time_string()} - {format % args}")


def build_handler(
    knowledge_base_path: Path = DEFAULT_KNOWLEDGE_BASE,
    sample_tickets_path: Path = DEFAULT_SAMPLE_TICKETS,
    db_path: Path = DEFAULT_DB_PATH,
    static_dir: Path = FRONTEND_DIR,
) -> type[SupportDeskHandler]:
    configured_knowledge_path = Path(os.environ.get("SUPPORT_DESK_KNOWLEDGE_PATH", str(knowledge_base_path)))
    knowledge_base = KnowledgeBase.from_path(configured_knowledge_path)
    llm_client = OpenAICompatibleClient.from_env() if _use_llm() else None
    orchestrator = SupportDeskOrchestrator(knowledge_base, llm_client=llm_client)
    store = build_ticket_store(db_path)

    class ConfiguredSupportDeskHandler(SupportDeskHandler):
        pass

    ConfiguredSupportDeskHandler.orchestrator = orchestrator
    ConfiguredSupportDeskHandler.store = store
    ConfiguredSupportDeskHandler.knowledge_base = knowledge_base
    ConfiguredSupportDeskHandler.sample_tickets_path = sample_tickets_path
    ConfiguredSupportDeskHandler.static_dir = static_dir
    return ConfiguredSupportDeskHandler


def _use_llm() -> bool:
    return os.environ.get("SUPPORT_DESK_USE_LLM", "").strip().lower() in {"1", "true", "yes", "on"}


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError("boolean value must be true or false")


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    handler = build_handler()
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Multi-Agent Support Desk running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run()
