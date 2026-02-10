"""Tests for Prometheus exporter."""

from datetime import datetime

from src.database import get_session, init_db
from src.models import ScraperMetric
from src.prometheus_exporter import ScraperMetricsCollector


def test_prometheus_collector(tmp_path, monkeypatch):
    """Test ScraperMetricsCollector collects metrics from database."""
    db_file = tmp_path / "prom.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    session = get_session()

    # Insert sample metrics
    now = datetime.utcnow()
    session.add_all(
        [
            ScraperMetric(
                source="github", action="fetch_success", value=5, created_at=now
            ),
            ScraperMetric(
                source="microsoft", action="jobs_added", value=3, created_at=now
            ),
        ]
    )
    session.commit()
    session.close()

    # Create collector and collect
    collector = ScraperMetricsCollector()
    metrics = list(collector.collect())

    # Should have at least one metric
    assert len(metrics) > 0

    # Check metric name
    metric = metrics[0]
    assert metric.name == "jobhunter_scraper_events_total"
    assert metric.documentation == "Total scraper events by source and action"

    # Check labels
    assert len(metric.samples) > 0


def test_prometheus_cli_command():
    """Test prometheus CLI command integration."""
    from unittest.mock import MagicMock, patch

    from click.testing import CliRunner

    from src.cli import cli

    runner = CliRunner()

    # Mock prometheus_client.start_http_server
    mock_http_server = MagicMock()
    with patch("prometheus_client.start_http_server", mock_http_server):
        with patch("src.cli.create_exporter"):
            # Simulate Ctrl+C
            with patch("time.sleep", side_effect=KeyboardInterrupt()):
                result = runner.invoke(cli, ["prometheus", "--port", "9090"])
                assert result.exit_code == 0
                assert "Prometheus exporter started" in result.output
                assert "9090" in result.output
