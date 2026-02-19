"""Tests for The Muse job board scraper."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.themuse_scraper import TheMuseScraper
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
    """Create The Muse scraper."""
    return TheMuseScraper(session)


# Sample The Muse API response
SAMPLE_MUSE_RESPONSE = {
    "page": 0,
    "page_count": 5,
    "results": [
        {
            "id": 11111,
            "name": "Senior Software Engineer",
            "company": {
                "name": "Acme Corp",
                "size": {"name": "Large Size"},
                "industries": [{"name": "Technology"}],
            },
            "locations": [{"name": "New York, NY"}],
            "categories": [{"name": "Software Engineering"}],
            "contents": (
                "<p>We are looking for a <strong>Senior Software Engineer</strong>.</p>"
                "<ul><li>5+ years of experience</li></ul>"
            ),
            "refs": {
                "landing_page": (
                    "https://www.themuse.com/jobs/" "acmecorp/senior-software-engineer"
                )
            },
            "publication_date": "2025-12-01T10:00:00Z",
        },
        {
            "id": 22222,
            "name": "Data Scientist - Remote",
            "company": {
                "name": "DataCo",
                "size": {"name": "Medium Size"},
                "industries": [{"name": "Data & Analytics"}],
            },
            "locations": [{"name": "Flexible / Remote"}],
            "categories": [{"name": "Data Science"}],
            "contents": "<p>Join our data science team.</p>",
            "refs": {
                "landing_page": (
                    "https://www.themuse.com/jobs/" "dataco/data-scientist-remote"
                )
            },
            "publication_date": "2025-11-15T08:30:00Z",
        },
    ],
}


class TestTheMuseScraper:
    """Tests for The Muse scraper."""

    def test_source_name(self, scraper):
        assert scraper._get_source_name() == "themuse"

    def test_parse_job_basic(self, scraper):
        raw_job = SAMPLE_MUSE_RESPONSE["results"][0]

        parsed = scraper._parse_job(raw_job)

        assert parsed["source_job_id"] == "11111"
        assert parsed["title"] == "Senior Software Engineer"
        assert parsed["company"] == "Acme Corp"
        assert parsed["location"] == "New York, NY"
        assert parsed["department"] == "Software Engineering"
        assert parsed["remote"] is None
        assert parsed["source_type"] == "aggregator"
        assert parsed["company_industry"] == "Technology"
        assert parsed["company_size"] == "Large Size"
        assert "themuse.com" in parsed["apply_url"]

    def test_parse_job_remote(self, scraper):
        raw_job = SAMPLE_MUSE_RESPONSE["results"][1]

        parsed = scraper._parse_job(raw_job)

        assert parsed["title"] == "Data Scientist - Remote"
        assert parsed["remote"] == "remote"
        assert parsed["location"] == "Flexible / Remote"

    def test_parse_job_strips_html(self, scraper):
        raw_job = SAMPLE_MUSE_RESPONSE["results"][0]

        parsed = scraper._parse_job(raw_job)

        assert "<p>" not in parsed["description"]
        assert "<strong>" not in parsed["description"]
        assert "Senior Software Engineer" in parsed["description"]

    def test_parse_job_posted_date(self, scraper):
        raw_job = SAMPLE_MUSE_RESPONSE["results"][0]

        parsed = scraper._parse_job(raw_job)

        assert isinstance(parsed["posted_date"], datetime)
        assert parsed["posted_date"].year == 2025
        assert parsed["posted_date"].month == 12

    def test_strip_html(self):
        assert TheMuseScraper._strip_html("<p>Hello <b>world</b></p>") == "Hello world"
        assert TheMuseScraper._strip_html("") == ""
        assert TheMuseScraper._strip_html("plain text") == "plain text"

    @patch("src.job_scrapers.themuse_scraper.requests.get")
    def test_fetch_jobs_success(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_MUSE_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)

        assert len(jobs) == 2
        assert jobs[0]["name"] == "Senior Software Engineer"

    @patch("src.job_scrapers.themuse_scraper.requests.get")
    def test_fetch_jobs_api_error(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.themuse_scraper.requests.get")
    def test_fetch_jobs_network_error(self, mock_get, scraper):
        import requests

        mock_get.side_effect = requests.RequestException("Connection timeout")

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.themuse_scraper.requests.get")
    def test_fetch_jobs_pagination_stops_at_page_count(self, mock_get, scraper):
        """Test pagination respects page_count from API."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "page": 0,
            "page_count": 1,
            "results": SAMPLE_MUSE_RESPONSE["results"],
        }
        mock_get.return_value = response

        jobs = scraper._fetch_jobs(max_pages=5)

        assert len(jobs) == 2
        assert mock_get.call_count == 1  # Only 1 page fetched

    @patch("src.job_scrapers.themuse_scraper.requests.get")
    def test_scrape_persists_jobs(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_MUSE_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper.scrape(max_retries=1, max_pages=1)

        assert len(jobs) == 2
        saved = scraper.session.query(Job).filter(Job.source == "themuse").all()
        assert len(saved) == 2

    @patch("src.job_scrapers.themuse_scraper.requests.get")
    def test_scrape_deduplicates(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_MUSE_RESPONSE
        mock_get.return_value = mock_response

        first = scraper.scrape(max_retries=1, max_pages=1)
        second = scraper.scrape(max_retries=1, max_pages=1)

        assert len(first) == 2
        assert len(second) == 0

        saved = scraper.session.query(Job).filter(Job.source == "themuse").all()
        assert len(saved) == 2
