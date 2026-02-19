"""Tests for background worker."""

from unittest.mock import MagicMock, patch

from src.worker import _match_job, _scrape_job, start_worker


def test_scrape_job_with_mock():
    """Test _scrape_job function with mocked scraper."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.return_value = []
    mock_scraper_cls.return_value = mock_instance

    with patch("src.worker.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}):
        _scrape_job("greenhouse")

    assert mock_scraper_cls.called
    assert mock_instance.scrape.called


def test_match_job_with_mock():
    """Test _match_job function with mocked session."""
    with patch("src.worker.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_session.query.return_value.all.side_effect = [[], []]  # No users, no jobs
        mock_get_session.return_value = mock_session

        # Should not raise even if no users/jobs
        _match_job()

        # Verify session was closed
        assert mock_session.close.called


def test_start_worker_returns_scheduler():
    """Test start_worker returns scheduler instance."""
    scheduler = start_worker(daemonize=False)
    assert scheduler is not None
    assert hasattr(scheduler, "add_job")
    assert hasattr(scheduler, "start")
    assert hasattr(scheduler, "shutdown")

    # Verify scrape jobs (one per DEFAULT_SOURCE) + 1 match job
    from src.job_scrapers.registry import DEFAULT_SOURCES

    assert len(scheduler.get_jobs()) == len(DEFAULT_SOURCES) + 1


def test_worker_cli_command():
    """Test worker CLI command integration."""
    from click.testing import CliRunner

    from src.cli import cli

    runner = CliRunner()

    # Mock the worker to avoid actually starting it
    with patch("src.cli.start_worker") as mock_start:
        with patch("src.cli.setup_signal_handlers"):
            mock_scheduler = MagicMock()
            mock_start.return_value = mock_scheduler

            # Simulate Ctrl+C by raising KeyboardInterrupt
            with patch("time.sleep", side_effect=KeyboardInterrupt()):
                result = runner.invoke(cli, ["worker"])
                assert result.exit_code == 0
                assert "Starting job-agent worker" in result.output
                assert mock_start.called
