"""Tests for incremental scraping and notifications."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.database import get_session, init_db
from src.incremental import IncrementalScraper, SimpleNotifier
from src.models import Job, JobMatch, User, UserPreferences


def test_incremental_scraper(tmp_path, monkeypatch):
    """Test IncrementalScraper filters by posted date."""
    db_file = tmp_path / "incremental.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    session = get_session()

    # Mock scraper to return jobs with different posted dates
    now = datetime.utcnow()
    old_job = Job(
        source="microsoft",
        source_job_id="old-1",
        title="Old Job",
        company="OldCo",
        posted_date=now - timedelta(days=2),
    )
    new_job = Job(
        source="microsoft",
        source_job_id="new-1",
        title="New Job",
        company="NewCo",
        posted_date=now - timedelta(hours=6),
    )
    session.add_all([old_job, new_job])
    session.commit()

    with patch("src.incremental.MicrosoftScraper") as MockScraper:
        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = [old_job, new_job]
        MockScraper.return_value = mock_scraper

        incremental = IncrementalScraper(session)
        count = incremental.scrape_incremental("microsoft", lookback_hours=24)

        # Should only count new_job as it's within 24 hours
        assert count == 1

    session.close()


def test_simple_notifier_high_matches(tmp_path, monkeypatch):
    """Test SimpleNotifier finds high-match jobs."""
    db_file = tmp_path / "notifier.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    init_db()
    session = get_session()

    # Create user and job
    user = User(name="Alice")
    prefs = UserPreferences(salary_min=80000)
    user.preferences = prefs
    session.add(user)
    session.commit()

    job = Job(
        source="github",
        source_job_id="job-1",
        title="Backend Engineer",
        company="Acme",
        location="SF",
    )
    session.add(job)
    session.commit()

    # Create high-match
    match = JobMatch(job_id=job.id, user_id=user.id, match_score=85.0)
    session.add(match)
    session.commit()

    # Test notifier
    notifier = SimpleNotifier(session)
    matches = notifier.notify_high_matches(user, min_score=80.0)

    assert len(matches) == 1
    assert matches[0][1].match_score == 85.0

    session.close()


def test_notification_format():
    """Test notification message formatting."""
    job = MagicMock()
    job.title = "Senior Engineer"
    job.company = "TechCorp"
    job.location = "NYC"
    job.remote = "hybrid"
    job.apply_url = "https://example.com/apply"

    match = MagicMock()
    match.match_score = 87.5

    notifier = SimpleNotifier(None)
    msg = notifier.format_notification(job, match)

    assert "Senior Engineer" in msg
    assert "TechCorp" in msg
    assert "87.5" in msg
    assert "NYC" in msg
    assert "hybrid" in msg
