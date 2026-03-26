"""Tests for AWS Lambda handler."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _set_env(tmp_path, monkeypatch):
    """Set Lambda environment variables for all tests."""
    db_path = str(tmp_path / "jobs.db")
    monkeypatch.setenv("SNS_TOPIC_ARN", "arn:aws:sns:eu-west-1:123:test-topic")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("MIN_MATCH_SCORE_NOTIFY", "70")


@pytest.fixture
def mock_sns_client():
    """Mock SNS client via the lazy getter."""
    mock = MagicMock()
    with patch("src.lambda_handler._get_sns", return_value=mock):
        yield mock


@pytest.fixture
def mock_scrapers():
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.return_value = []
    mock_instance.last_raw_count = 0
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP",
        {"greenhouse": mock_scraper_cls, "lever": mock_scraper_cls},
    ):
        with patch(
            "src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse", "lever"]
        ):
            yield mock_scraper_cls, mock_instance


def test_handler_returns_summary(mock_sns_client, mock_scrapers):
    """Test handler returns a well-formed summary dict."""
    from src.lambda_handler import lambda_handler

    result = lambda_handler({}, None)

    assert result["jobs_scraped"] == 0
    assert result["matches_computed"] == 0
    assert "scrape_errors" in result
    assert "high_score_matches" in result


def test_handler_scraper_failure_recorded(mock_sns_client):
    """Test that a failing scraper is listed in scrape_errors."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.side_effect = Exception("Scraper broke")
    mock_instance.last_raw_count = 0
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}
    ):
        with patch("src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse"]):
            from src.lambda_handler import lambda_handler

            result = lambda_handler({}, None)

            assert "greenhouse" in result["scrape_errors"]


def test_handler_zero_results_scrapers_reported(mock_sns_client):
    """Test that scrapers returning 0 raw results are flagged."""
    mock_scraper_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.scrape.return_value = []
    mock_instance.last_raw_count = 0
    mock_scraper_cls.return_value = mock_instance

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP", {"greenhouse": mock_scraper_cls}
    ):
        with patch("src.job_scrapers.registry.DEFAULT_SOURCES", ["greenhouse"]):
            from src.lambda_handler import lambda_handler

            result = lambda_handler({}, None)

            assert "greenhouse" in result["zero_result_scrapers"]


def test_notify_sends_sns(mock_sns_client):
    """Test SNS notification is sent."""
    from src.lambda_handler import _notify

    _notify("arn:aws:sns:eu-west-1:123:topic", "Test Subject", "Test message")

    mock_sns_client.publish.assert_called_once_with(
        TopicArn="arn:aws:sns:eu-west-1:123:topic",
        Subject="Test Subject",
        Message="Test message",
    )


def test_notify_skipped_without_topic_arn(mock_sns_client):
    """Test notification is skipped when topic ARN is empty."""
    from src.lambda_handler import _notify

    _notify("", "Subject", "Message")
    mock_sns_client.publish.assert_not_called()


def test_scraper_failure_does_not_block_other_scrapers(mock_sns_client):
    """A failing scraper must not prevent other scrapers from running."""
    failing_cls = MagicMock()
    failing_cls.return_value.scrape.side_effect = Exception("network error")
    failing_cls.return_value.last_raw_count = 0

    ok_cls = MagicMock()
    ok_cls.return_value.scrape.return_value = []
    ok_cls.return_value.last_raw_count = 5

    with patch(
        "src.job_scrapers.registry.SCRAPER_MAP", {"bad": failing_cls, "ok": ok_cls}
    ):
        with patch("src.job_scrapers.registry.DEFAULT_SOURCES", ["bad", "ok"]):
            from src.lambda_handler import lambda_handler

            result = lambda_handler({}, None)

    assert "bad" in result["scrape_errors"]
    assert "ok" not in result["scrape_errors"]
    ok_cls.return_value.scrape.assert_called_once()


def test_stale_jobs_are_deactivated(
    mock_sns_client, mock_scrapers, tmp_path, monkeypatch
):
    """Jobs not seen for >30 days must be marked is_active=False after a run."""
    from datetime import datetime, timedelta

    db_path = str(tmp_path / "expiry.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from src.database import get_session, init_db
    from src.models import Job

    init_db()
    session = get_session()

    fresh = Job(source="test", source_job_id="fresh", title="Fresh Job", company="A")
    stale = Job(
        source="test",
        source_job_id="stale",
        title="Stale Job",
        company="B",
        scraped_at=datetime.utcnow() - timedelta(days=31),
    )
    session.add_all([fresh, stale])
    session.commit()
    session.close()

    from src.lambda_handler import lambda_handler

    lambda_handler({}, None)

    session = get_session()
    fresh_job = session.query(Job).filter(Job.source_job_id == "fresh").first()
    stale_job = session.query(Job).filter(Job.source_job_id == "stale").first()
    session.close()

    assert fresh_job.is_active is True
    assert stale_job.is_active is False


def test_matching_is_scoped_per_user(
    mock_sns_client, mock_scrapers, tmp_path, monkeypatch
):
    """Regression: jobs matched for user A must also be matched for user B.

    Previously the query found jobs with *no* JobMatch row globally, so once
    user A's matches were written, those jobs were invisible to user B.
    """
    db_path = str(tmp_path / "multi_user.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from src.database import get_session, init_db
    from src.models import Job, User, UserPreferences

    init_db()
    session = get_session()

    # Two approved users with minimal preferences
    for uid, email in [(1, "alice@example.com"), (2, "bob@example.com")]:
        u = User(id=uid, email=email, is_approved=True)
        prefs = UserPreferences(
            user_id=uid,
            target_titles=["Engineer"],
            experience_level="senior",
            remote_preference="remote",
        )
        session.add(u)
        session.add(prefs)

    # Two jobs with no existing matches
    for i in range(2):
        session.add(
            Job(
                source="greenhouse",
                source_job_id=f"job-{i}",
                title="Software Engineer",
                company="Acme",
                description="We need a senior engineer.",
            )
        )
    session.commit()
    session.close()

    from src.lambda_handler import lambda_handler

    result = lambda_handler({}, None)

    # Both users should have been scored against both jobs
    session = get_session()
    from src.models import JobMatch

    matches_by_user = {
        row.user_id: row.cnt
        for row in session.query(
            JobMatch.user_id, __import__("sqlalchemy").func.count().label("cnt")
        ).group_by(JobMatch.user_id)
    }
    session.close()

    assert matches_by_user.get(1) == 2, "User 1 should have 2 matches"
    assert matches_by_user.get(2) == 2, "User 2 should have 2 matches"
    assert result["matches_computed"] == 4
