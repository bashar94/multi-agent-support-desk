import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from supportdesk.database import build_ticket_store
from supportdesk.storage import TicketStore


class DatabaseFactoryTest(unittest.TestCase):
    def test_uses_default_sqlite_store_without_database_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {}, clear=True):
                store = build_ticket_store(Path(temp_dir) / "desk.sqlite3")

            self.assertIsInstance(store, TicketStore)

    def test_uses_sqlite_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "desk.sqlite3"
            with patch.dict(os.environ, {"SUPPORT_DESK_DATABASE_URL": f"sqlite:///{db_path}"}, clear=False):
                store = build_ticket_store(Path(temp_dir) / "ignored.sqlite3")

            self.assertIsInstance(store, TicketStore)
            self.assertEqual(store.db_path, db_path)

    def test_rejects_unknown_database_url_scheme(self) -> None:
        with patch.dict(os.environ, {"SUPPORT_DESK_DATABASE_URL": "mysql://example"}, clear=False):
            with self.assertRaises(ValueError):
                build_ticket_store(Path("desk.sqlite3"))


if __name__ == "__main__":
    unittest.main()
