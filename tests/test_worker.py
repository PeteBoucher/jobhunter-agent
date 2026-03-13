"""Tests for background worker."""

import signal
from unittest.mock import MagicMock, patch

import src.worker as worker_module
from src.worker import (
    _match_job,
    _scrape_job,
    setup_signal_handlers,
    start_worker,
    stop_worker,
)


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


def test_scrape_job_unknown_source_logs_warning():
    """Unknown source should log a warning and return without raising."""
    with patch("src.worker.get_session") as mock_get_session:
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        with patch("src.worker.SCRAPER_MAP", {}):
            _scrape_job("nonexistent_source")  # must not raise
        mock_session.close.assert_called_once()


def test_scrape_job_exception_is_caught():
    """Exceptions from scraper are caught, session still closed."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.side_effect = RuntimeError("scraper blew up")
    mock_scraper_cls.return_value = mock_instance

    with patch("src.worker.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}):
        with patch("src.worker.get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session
            _scrape_job("greenhouse")  # must not propagate

        mock_session.close.assert_called_once()


def test_match_job_specific_user(monkeypatch, tmp_path):
    """_match_job with a user_id filters to just that user."""
    db_url = f"sqlite:///{tmp_path}/worker_test.db"
    monkeypatch.setenv("DATABASE_URL", db_url)

    from src.database import get_session, init_db

    init_db()
    session = get_session()

    from src.models import Job, User

    user = User(name="Test")
    job = Job(title="Eng", company="Co", source="test")
    session.add_all([user, job])
    session.commit()
    user_id = user.id
    session.close()

    with patch("src.worker.compute_match_for_user") as mock_match:
        with patch("src.worker.get_session", return_value=get_session()):
            _match_job(user_id=user_id)

    assert mock_match.called


def test_match_job_exception_is_caught():
    """Exceptions during matching are caught, session still closed."""
    with patch("src.worker.get_session") as mock_get_session:
        mock_session = MagicMock()
        # Return users but raise on jobs query
        mock_session.query.return_value.all.side_effect = [
            [MagicMock()],
            RuntimeError("db error"),
        ]
        mock_session.query.return_value.filter.return_value.all.side_effect = (
            RuntimeError("db error")
        )
        mock_get_session.return_value = mock_session

        _match_job()  # must not propagate

        mock_session.close.assert_called_once()


def test_start_worker_daemonize_starts_scheduler():
    """daemonize=True should call scheduler.start()."""
    mock_scheduler = MagicMock()
    with patch("src.worker.BackgroundScheduler", return_value=mock_scheduler):
        result = start_worker(daemonize=True)

    mock_scheduler.start.assert_called_once()
    assert result is mock_scheduler


def test_stop_worker():
    """stop_worker shuts down and clears the global scheduler."""
    mock_scheduler = MagicMock()
    worker_module._scheduler = mock_scheduler

    stop_worker()

    mock_scheduler.shutdown.assert_called_once()
    assert worker_module._scheduler is None


def test_stop_worker_no_op_when_not_started():
    """stop_worker is a no-op when no scheduler is running."""
    worker_module._scheduler = None
    stop_worker()  # must not raise


def test_setup_signal_handlers_registers_sigint():
    """Signal handlers must be registered for SIGINT and SIGTERM."""
    with patch("signal.signal") as mock_signal:
        setup_signal_handlers()

    calls = {call[0][0] for call in mock_signal.call_args_list}
    assert signal.SIGINT in calls
    assert signal.SIGTERM in calls


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
