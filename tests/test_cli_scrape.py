from click.testing import CliRunner


def test_scrape_cli_monkeypatched(monkeypatch, tmp_path):
    """Ensure `job-agent scrape` runs and handles scrapers without network calls.

    We monkeypatch the SCRAPER_MAP in the registry to use dummy scrapers.
    """
    # Use an in-memory SQLite DB so the test never dials out to Neon
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test.db")

    from src.database import init_db

    init_db()

    # Dummy scraper
    class DummyScraper:
        def __init__(self, session):
            pass

        def scrape(self, **kwargs):
            return []

        def scrape_by_keywords(self, keywords):
            return 0

    # Patch the names as bound in src.cli (not the registry originals), because
    # src.cli may already be cached and holds its own references via
    # `from src.job_scrapers.registry import SCRAPER_MAP, DEFAULT_SOURCES`.
    from src.cli import cli

    dummy_map = {"greenhouse": DummyScraper, "lever": DummyScraper}
    monkeypatch.setattr("src.cli.SCRAPER_MAP", dummy_map)
    monkeypatch.setattr("src.cli.DEFAULT_SOURCES", ["greenhouse", "lever"])

    runner = CliRunner()
    result = runner.invoke(cli, ["scrape"])
    assert result.exit_code == 0
