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

    # Patch the registry used by the CLI
    dummy_map = {"greenhouse": DummyScraper, "lever": DummyScraper}
    monkeypatch.setattr("src.job_scrapers.registry.SCRAPER_MAP", dummy_map)
    monkeypatch.setattr(
        "src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse", "lever"]
    )

    from src.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["scrape"])
    assert result.exit_code == 0
