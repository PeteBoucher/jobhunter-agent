"""Tests for Adzuna job aggregator scraper."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.adzuna_scraper import LOCATION_TO_COUNTRY_CODE, AdzunaScraper
from src.models import Job, UserPreferences


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
    """Create Adzuna scraper with test credentials."""
    return AdzunaScraper(
        session,
        countries=["gb"],
        search_terms=["innovation lead"],
        app_id="test_id",
        app_key="test_key",
    )


@pytest.fixture
def scraper_no_creds(session):
    """Create Adzuna scraper without credentials."""
    return AdzunaScraper(
        session,
        countries=["gb"],
        search_terms=["innovation lead"],
        app_id="",
        app_key="",
    )


# Sample Adzuna API response
SAMPLE_ADZUNA_RESPONSE = {
    "results": [
        {
            "id": "abc123",
            "title": "Senior Python Developer",
            "company": {"display_name": "TechCorp"},
            "location": {"display_name": "London, UK"},
            "description": "We are looking for an experienced Python developer.",
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/abc123",
            "salary_min": 70000,
            "salary_max": 90000,
            "created": "2025-12-01T10:00:00Z",
            "category": {"label": "IT Jobs"},
        },
        {
            "id": "def456",
            "title": "Remote Backend Engineer",
            "company": {"display_name": "StartupInc"},
            "location": {"display_name": "Remote"},
            "description": "Join our remote-first engineering team.",
            "redirect_url": "https://www.adzuna.co.uk/jobs/details/def456",
            "salary_min": None,
            "salary_max": None,
            "created": "2025-11-20T14:30:00Z",
            "category": {"label": "Engineering Jobs"},
        },
    ]
}


class TestSearchTermsFromPrefs:
    """Tests for BaseScraper._search_terms_from_prefs and _countries_from_prefs."""

    def test_returns_titles_from_all_users(self, session):
        session.add(UserPreferences(target_titles=["Product Manager", "Product Owner"]))
        session.add(UserPreferences(target_titles=["Software Engineer"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        terms = scraper._search_terms_from_prefs()
        assert "Product Manager" in terms
        assert "Product Owner" in terms
        assert "Software Engineer" in terms

    def test_deduplicates_case_insensitively(self, session):
        session.add(UserPreferences(target_titles=["Product Manager"]))
        session.add(UserPreferences(target_titles=["product manager"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        terms = scraper._search_terms_from_prefs()
        assert len([t for t in terms if t.lower() == "product manager"]) == 1

    def test_falls_back_when_no_prefs(self, session):
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        terms = scraper._search_terms_from_prefs(fallback=["my fallback"])
        assert terms == ["my fallback"]

    def test_skips_null_and_empty_titles(self, session):
        session.add(UserPreferences(target_titles=None))
        session.add(UserPreferences(target_titles=[]))
        session.add(UserPreferences(target_titles=["Engineer"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        terms = scraper._search_terms_from_prefs()
        assert terms == ["Engineer"]

    def test_countries_from_uk_location(self, session):
        session.add(UserPreferences(preferred_locations=["London, UK"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        codes = scraper._countries_from_prefs(LOCATION_TO_COUNTRY_CODE)
        assert "gb" in codes

    def test_countries_deduplicates(self, session):
        session.add(UserPreferences(preferred_locations=["London, UK"]))
        session.add(UserPreferences(preferred_locations=["United Kingdom"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        codes = scraper._countries_from_prefs(LOCATION_TO_COUNTRY_CODE)
        assert codes.count("gb") == 1

    def test_countries_from_copenhagen_location(self, session):
        session.add(UserPreferences(preferred_locations=["Copenhagen, Denmark"]))
        session.add(UserPreferences(preferred_locations=["copenhagen"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        codes = scraper._countries_from_prefs(LOCATION_TO_COUNTRY_CODE)
        assert codes.count("dk") == 1

    def test_countries_from_berlin_location(self, session):
        session.add(UserPreferences(preferred_locations=["Lüneburg, Germany"]))
        session.add(UserPreferences(preferred_locations=["Berlin"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        codes = scraper._countries_from_prefs(LOCATION_TO_COUNTRY_CODE)
        assert codes.count("de") == 1

    def test_countries_fallback_when_no_match(self, session):
        session.add(UserPreferences(preferred_locations=["Remote"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        codes = scraper._countries_from_prefs(LOCATION_TO_COUNTRY_CODE, fallback=["gb"])
        assert codes == ["gb"]

    def test_scraper_init_uses_db_terms_when_none_passed(self, session):
        session.add(UserPreferences(target_titles=["CTO"]))
        session.commit()
        scraper = AdzunaScraper(session, app_id="x", app_key="x")
        assert scraper.search_terms == ["CTO"]


class TestAdzunaScraper:
    """Tests for Adzuna scraper."""

    def test_source_name(self, scraper):
        assert scraper._get_source_name() == "adzuna"

    def test_parse_job_basic(self, scraper):
        raw_job = SAMPLE_ADZUNA_RESPONSE["results"][0].copy()
        raw_job["_country"] = "gb"

        parsed = scraper._parse_job(raw_job)

        assert parsed["source_job_id"] == "abc123"
        assert parsed["title"] == "Senior Python Developer"
        assert parsed["company"] == "TechCorp"
        assert parsed["location"] == "London, UK"
        assert parsed["remote"] is None
        assert parsed["salary_min"] == 70000
        assert parsed["salary_max"] == 90000
        assert parsed["source_type"] == "aggregator"
        assert parsed["department"] == "IT Jobs"

    def test_parse_job_remote(self, scraper):
        raw_job = SAMPLE_ADZUNA_RESPONSE["results"][1].copy()
        raw_job["_country"] = "gb"

        parsed = scraper._parse_job(raw_job)

        assert parsed["title"] == "Remote Backend Engineer"
        assert parsed["remote"] == "remote"

    def test_parse_job_posted_date(self, scraper):
        raw_job = SAMPLE_ADZUNA_RESPONSE["results"][0].copy()
        raw_job["_country"] = "gb"

        parsed = scraper._parse_job(raw_job)

        assert isinstance(parsed["posted_date"], datetime)
        assert parsed["posted_date"].year == 2025
        assert parsed["posted_date"].month == 12

    def test_no_credentials_returns_empty(self, scraper_no_creds):
        jobs = scraper_no_creds._fetch_jobs()
        assert jobs == []

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_fetch_jobs_success(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_ADZUNA_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()

        assert len(jobs) == 2
        assert jobs[0]["_country"] == "gb"
        assert jobs[0]["title"] == "Senior Python Developer"

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_fetch_jobs_auth_failure(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_fetch_jobs_rate_limit(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_fetch_jobs_network_error(self, mock_get, scraper):
        import requests

        mock_get.side_effect = requests.RequestException("Connection timeout")

        jobs = scraper._fetch_jobs()
        assert len(jobs) == 0

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_fetch_jobs_pagination_stops_on_empty(self, mock_get, scraper):
        """Test pagination stops when no more results."""
        first_response = MagicMock()
        first_response.status_code = 200
        first_response.json.return_value = SAMPLE_ADZUNA_RESPONSE

        empty_response = MagicMock()
        empty_response.status_code = 200
        empty_response.json.return_value = {"results": []}

        mock_get.side_effect = [first_response, empty_response]

        jobs = scraper._fetch_jobs(max_pages=3)
        assert len(jobs) == 2  # Only first page results

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_scrape_persists_jobs(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_ADZUNA_RESPONSE
        mock_get.return_value = mock_response

        jobs = scraper.scrape(max_retries=1)

        assert len(jobs) == 2
        saved = scraper.session.query(Job).filter(Job.source == "adzuna").all()
        assert len(saved) == 2

    @patch("src.job_scrapers.adzuna_scraper.requests.get")
    def test_scrape_deduplicates(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = SAMPLE_ADZUNA_RESPONSE
        mock_get.return_value = mock_response

        first = scraper.scrape(max_retries=1)
        second = scraper.scrape(max_retries=1)

        assert len(first) == 2
        assert len(second) == 0

        saved = scraper.session.query(Job).filter(Job.source == "adzuna").all()
        assert len(saved) == 2
