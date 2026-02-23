"""Tests for Reed.co.uk job board scraper."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.reed_scraper import ReedScraper
from src.models import Job


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = f"sqlite:///{tmpdir}/test.db"
        import os

        os.environ["DATABASE_URL"] = db_path
        init_db()
        yield db_path


@pytest.fixture
def session(temp_db):
    """Get database session."""
    session = get_session()
    yield session
    session.close()


@pytest.fixture
def scraper(session):
    """Create Reed scraper with test API key."""
    return ReedScraper(
        session,
        api_key="test_api_key",
        search_terms=["innovation lead"],
    )


@pytest.fixture
def scraper_no_key(session):
    """Create Reed scraper without API key."""
    return ReedScraper(session, api_key="", search_terms=["innovation lead"])


SAMPLE_REED_RESPONSE = {
    "results": [
        {
            "jobId": 12345,
            "employerName": "Global Corp",
            "jobTitle": "Innovation Lead",
            "locationName": "London",
            "minimumSalary": 80000.0,
            "maximumSalary": 100000.0,
            "date": "01/02/2026",
            "jobDescription": "Lead innovation initiatives across the enterprise.",
            "jobUrl": "https://www.reed.co.uk/jobs/innovation-lead/12345",
        },
        {
            "jobId": 67890,
            "employerName": "Remote First Ltd",
            "jobTitle": "Enterprise Architect",
            "locationName": "Remote",
            "minimumSalary": None,
            "maximumSalary": None,
            "date": "15/01/2026",
            "jobDescription": "Remote enterprise architecture role.",
            "jobUrl": "https://www.reed.co.uk/jobs/enterprise-architect/67890",
        },
    ]
}


class TestReedScraper:
    """Tests for Reed scraper."""

    def test_source_name(self, scraper):
        assert scraper._get_source_name() == "reed"

    def test_parse_job_basic(self, scraper):
        raw_job = SAMPLE_REED_RESPONSE["results"][0]
        parsed = scraper._parse_job(raw_job)

        assert parsed["source_job_id"] == "12345"
        assert parsed["title"] == "Innovation Lead"
        assert parsed["company"] == "Global Corp"
        assert parsed["location"] == "London"
        assert parsed["remote"] is None
        assert parsed["salary_min"] == 80000.0
        assert parsed["salary_max"] == 100000.0
        assert parsed["source_type"] == "aggregator"
        assert (
            parsed["apply_url"] == "https://www.reed.co.uk/jobs/innovation-lead/12345"
        )

    def test_parse_job_remote(self, scraper):
        raw_job = SAMPLE_REED_RESPONSE["results"][1]
        parsed = scraper._parse_job(raw_job)

        assert parsed["remote"] == "remote"
        assert parsed["salary_min"] is None
        assert parsed["salary_max"] is None

    def test_parse_job_date(self, scraper):
        raw_job = SAMPLE_REED_RESPONSE["results"][0]
        parsed = scraper._parse_job(raw_job)

        assert isinstance(parsed["posted_date"], datetime)
        assert parsed["posted_date"].year == 2026
        assert parsed["posted_date"].month == 2

    def test_no_api_key_returns_empty(self, scraper_no_key):
        jobs = scraper_no_key._fetch_jobs()
        assert jobs == []

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_fetch_jobs_success(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_REED_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()

        assert len(jobs) == 2
        assert jobs[0]["jobTitle"] == "Innovation Lead"

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_fetch_jobs_auth_failure(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_fetch_jobs_rate_limit(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_fetch_deduplicates_across_terms(self, mock_get, scraper):
        """Jobs returned by multiple search terms are deduplicated."""
        scraper.search_terms = ["innovation lead", "enterprise architect"]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_REED_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 2  # Not 4, despite two search terms returning same jobs

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_fetch_stops_on_empty_results(self, mock_get, scraper):
        first = MagicMock()
        first.status_code = 200
        first.json.return_value = SAMPLE_REED_RESPONSE

        empty = MagicMock()
        empty.status_code = 200
        empty.json.return_value = {"results": []}

        mock_get.side_effect = [first, empty]
        jobs = scraper._fetch_jobs()
        assert len(jobs) == 2

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_scrape_persists_jobs(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_REED_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper.scrape(max_retries=1)

        assert len(jobs) == 2
        saved = scraper.session.query(Job).filter(Job.source == "reed").all()
        assert len(saved) == 2

    @patch("src.job_scrapers.reed_scraper.requests.get")
    def test_scrape_deduplicates(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_REED_RESPONSE
        mock_get.return_value = mock_response

        first = scraper.scrape(max_retries=1)
        second = scraper.scrape(max_retries=1)

        assert len(first) == 2
        assert len(second) == 0
        saved = scraper.session.query(Job).filter(Job.source == "reed").all()
        assert len(saved) == 2
