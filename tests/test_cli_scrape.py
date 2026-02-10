from click.testing import CliRunner


def test_scrape_cli_monkeypatched(monkeypatch):
    """Ensure `job-agent scrape` runs and handles scrapers without network calls.

    We monkeypatch scraper classes used by `src.cli` to harmless dummies.
    """

    # Dummy scrapers
    class DummyScraper:
        def __init__(self, session):
            pass

        def scrape(self, **kwargs):
            return []

        def scrape_by_keywords(self, keywords):
            return 0

    # Patch the scraper classes in src.cli
    monkeypatch.setattr("src.cli.GitHubJobsScraper", DummyScraper)
    monkeypatch.setattr("src.cli.MicrosoftScraper", DummyScraper)

    from src.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["scrape"])
    assert result.exit_code == 0
