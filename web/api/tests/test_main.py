"""Tests for the app's startup lifespan (table auto-creation)."""

from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app


class TestLifespanTableCreation:
    def test_app_starts_normally(self):
        """Sanity: the lifespan's create_all() doesn't block normal startup."""
        with TestClient(app) as client:
            resp = client.get("/openapi.json")
            assert resp.status_code == 200

    def test_startup_survives_a_broken_db_connection(self):
        """A DB hiccup at boot (e.g. DATABASE_URL momentarily unreachable) must
        not crash the whole API — Render would crash-loop it. This is also
        what protects the test suite from other test modules' DATABASE_URL
        pollution (several root-level tests set it directly without a
        monkeypatch teardown, e.g. tests/test_adzuna_scraper.py)."""
        with patch("main.create_engine_instance", side_effect=RuntimeError("boom")):
            with TestClient(app) as client:
                resp = client.get("/openapi.json")
                assert resp.status_code == 200
