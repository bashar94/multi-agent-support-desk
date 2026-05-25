"""Project paths and runtime defaults."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DEFAULT_KNOWLEDGE_BASE = DATA_DIR / "knowledge_base.json"
DEFAULT_SAMPLE_TICKETS = DATA_DIR / "sample_tickets.json"
DEFAULT_DB_PATH = PROJECT_ROOT / os.environ.get("SUPPORT_DESK_DB", ".data/support_desk.sqlite3")
DEFAULT_HOST = os.environ.get("SUPPORT_DESK_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("SUPPORT_DESK_PORT", "8080"))
