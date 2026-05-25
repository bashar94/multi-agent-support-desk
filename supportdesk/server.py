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
from supportdesk.orchestrator import SupportDeskOrchestrator
from supportdesk.storage import TicketStore


class SupportDeskHandler(BaseHTTPRequestHandler):
    orchestrator: SupportDeskOrchestrator
    store: TicketStore
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
                payload = self._read_json()
                ticket = Ticket.from_payload(payload)
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

            self._send_json({"error": "route not found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _load_sample_tickets(self) -> list[dict[str, Any]]:
        with self.sample_tickets_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

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
    knowledge_base = KnowledgeBase.from_json(knowledge_base_path)
    llm_client = OpenAICompatibleClient.from_env() if _use_llm() else None
    orchestrator = SupportDeskOrchestrator(knowledge_base, llm_client=llm_client)
    store = TicketStore(db_path)

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


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    handler = build_handler()
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Multi-Agent Support Desk running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run()
