"""Tests for Lever job board scraper."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.lever_scraper import LeverScraper
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
    """Create Lever scraper with a small set of companies."""
    return LeverScraper(session, company_slugs=["testco"])


# Sample Lever API response (list of postings)
SAMPLE_LEVER_RESPONSE = [
    {
        "id": "aaa-bbb-ccc-111",
        "text": "Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/testco/aaa-bbb-ccc-111",
        "applyUrl": "https://jobs.lever.co/testco/aaa-bbb-ccc-111/apply",
        "categories": {
            "commitment": "Full-time",
            "department": "Engineering",
            "location": "New York, NY",
            "team": "Platform",
        },
        "descriptionPlain": (
            "We are looking for a Backend Engineer with experience in "
            "Python, PostgreSQL, and AWS. You will build scalable "
            "microservices using Docker and Kubernetes."
        ),
        "description": "<p>We are looking for a Backend Engineer...</p>",
        "lists": [
            {
                "text": "Requirements",
                "content": (
                    "5+ years of backend development experience\n"
                    "Strong Python and SQL skills\n"
                    "Experience with cloud platforms (AWS/GCP)"
                ),
            },
            {
                "text": "Nice to have",
                "content": "Experience with Go\nFamiliarity with ML pipelines",
            },
        ],
        "createdAt": 1701388800000,  # 2023-12-01T00:00:00Z
    },
    {
        "id": "ddd-eee-fff-222",
        "text": "Senior Data Scientist - Remote",
        "hostedUrl": "https://jobs.lever.co/testco/ddd-eee-fff-222",
        "applyUrl": "https://jobs.lever.co/testco/ddd-eee-fff-222/apply",
        "categories": {
            "commitment": "Full-time",
            "department": "Data",
            "location": "Remote",
            "team": "ML",
        },
        "descriptionPlain": (
            "Join our data science team to build machine learning models "
            "using PyTorch and TensorFlow. Experience with Spark and "
            "data engineering pipelines preferred."
        ),
        "lists": [],
        "createdAt": 1700784000000,  # 2023-11-24T00:00:00Z
    },
]


class TestLeverScraper:
    """Tests for Lever scraper."""

    def test_source_name(self, scraper):
        """Test that Lever scraper has correct source name."""
        assert scraper._get_source_name() == "lever"

    def test_parse_job_basic(self, scraper):
        """Test parsing a standard Lever posting."""
        raw_job = SAMPLE_LEVER_RESPONSE[0].copy()
        raw_job["_company_slug"] = "testco"

        parsed = scraper._parse_job(raw_job)

        assert parsed["source_job_id"] == "aaa-bbb-ccc-111"
        assert parsed["title"] == "Backend Engineer"
        assert parsed["company"] == "Testco"
        assert parsed["location"] == "New York, NY"
        assert parsed["department"] == "Engineering"
        assert parsed["remote"] is None
        assert parsed["source_type"] == "company_portal"
        assert (
            parsed["apply_url"] == "https://jobs.lever.co/testco/aaa-bbb-ccc-111/apply"
        )

    def test_parse_job_remote(self, scraper):
        """Test parsing a remote job correctly detects remote status."""
        raw_job = SAMPLE_LEVER_RESPONSE[1].copy()
        raw_job["_company_slug"] = "testco"

        parsed = scraper._parse_job(raw_job)

        assert parsed["title"] == "Senior Data Scientist - Remote"
        assert parsed["remote"] == "remote"
        assert parsed["location"] == "Remote"

    def test_parse_job_posted_date(self, scraper):
        """Test that posted date is parsed from epoch milliseconds."""
        raw_job = SAMPLE_LEVER_RESPONSE[0].copy()
        raw_job["_company_slug"] = "testco"

        parsed = scraper._parse_job(raw_job)

        assert isinstance(parsed["posted_date"], datetime)
        assert parsed["posted_date"].year == 2023
        assert parsed["posted_date"].month == 12

    def test_parse_job_requirements_from_lists(self, scraper):
        """Test that requirements are extracted from Lever lists."""
        raw_job = SAMPLE_LEVER_RESPONSE[0].copy()
        raw_job["_company_slug"] = "testco"

        parsed = scraper._parse_job(raw_job)

        assert parsed["requirements"] is not None
        assert len(parsed["requirements"]) > 0
        # Should contain requirement lines from the "Requirements" list
        assert any("backend" in r.lower() for r in parsed["requirements"])

    def test_parse_job_requirements_fallback_to_description(self, scraper):
        """Test fallback to keyword extraction when no requirement lists."""
        raw_job = SAMPLE_LEVER_RESPONSE[1].copy()
        raw_job["_company_slug"] = "testco"

        parsed = scraper._parse_job(raw_job)

        # Should fall back to keyword extraction from description
        assert parsed["requirements"] is not None
        assert "machine learning" in parsed["requirements"]
        assert "pytorch" in parsed["requirements"]

    @patch("src.job_scrapers.lever_scraper.requests.get")
    def test_fetch_jobs_success(self, mock_get, scraper):
        """Test successful job fetching from Lever API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_LEVER_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()

        assert len(jobs) == 2
        assert jobs[0]["_company_slug"] == "testco"
        assert jobs[0]["text"] == "Backend Engineer"

    @patch("src.job_scrapers.lever_scraper.requests.get")
    def test_fetch_jobs_404(self, mock_get, scraper):
        """Test handling of 404 (company not found)."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()

        assert len(jobs) == 0

    @patch("src.job_scrapers.lever_scraper.requests.get")
    def test_fetch_jobs_network_error(self, mock_get, scraper):
        """Test handling of network errors."""
        import requests

        mock_get.side_effect = requests.RequestException("Connection refused")

        jobs = scraper._fetch_jobs()

        assert len(jobs) == 0

    @patch("src.job_scrapers.lever_scraper.requests.get")
    def test_scrape_persists_jobs(self, mock_get, scraper):
        """Test that scrape() persists jobs to database."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_LEVER_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper.scrape(max_retries=1)

        assert len(jobs) == 2

        saved = scraper.session.query(Job).filter(Job.source == "lever").all()
        assert len(saved) == 2

    @patch("src.job_scrapers.lever_scraper.requests.get")
    def test_scrape_deduplicates(self, mock_get, scraper):
        """Test that scraping twice doesn't create duplicates."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_LEVER_RESPONSE
        mock_get.return_value = mock_response

        first = scraper.scrape(max_retries=1)
        second = scraper.scrape(max_retries=1)

        assert len(first) == 2
        assert len(second) == 0

        saved = scraper.session.query(Job).filter(Job.source == "lever").all()
        assert len(saved) == 2

    @patch("src.job_scrapers.lever_scraper.requests.get")
    def test_scrape_by_keywords(self, mock_get, scraper):
        """Test keyword filtering."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_LEVER_RESPONSE
        mock_get.return_value = mock_response

        count = scraper.scrape_by_keywords(["data scientist"])

        assert count == 1  # Only the "Senior Data Scientist" matches

    def test_extract_requirements(self, scraper):
        """Test requirement extraction from description text."""
        description = "Experience with Python, Docker, and AWS required."
        reqs = scraper._extract_requirements(description)

        assert "python" in reqs
        assert "docker" in reqs
        assert "aws" in reqs

    def test_extract_requirements_empty(self, scraper):
        """Test requirement extraction with no matches."""
        reqs = scraper._extract_requirements("No tech skills here.")
        assert reqs is None

    def test_extract_requirements_from_lists(self, scraper):
        """Test structured list extraction."""
        raw_job = {
            "lists": [
                {
                    "text": "What you'll need",
                    "content": "5+ years Python\n"
                    "Experience with AWS\n"
                    "Strong SQL skills",
                }
            ]
        }
        reqs = scraper._extract_requirements_from_lists(raw_job)
        assert reqs is not None
        assert len(reqs) == 3

    def test_extract_requirements_from_lists_empty(self, scraper):
        """Test structured list extraction with no requirement sections."""
        raw_job = {
            "lists": [
                {
                    "text": "Benefits",
                    "content": "Health insurance\nUnlimited PTO",
                }
            ]
        }
        reqs = scraper._extract_requirements_from_lists(raw_job)
        assert reqs is None
