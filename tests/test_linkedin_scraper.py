"""Tests for LinkedIn job board scraper."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.linkedin_scraper import LinkedInScraper
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
    """Create LinkedIn scraper with a single search term."""
    return LinkedInScraper(
        session,
        search_terms=["innovation lead"],
        locations=["United Kingdom"],
    )


# Minimal HTML fragment matching LinkedIn's current card structure
SAMPLE_LINKEDIN_HTML = """
<ul>
  <li>
    <div class="base-card base-card--link base-search-card job-search-card"
         data-entity-urn="urn:li:jobPosting:1001">
      <a class="base-card__full-link"
         href="https://uk.linkedin.com/jobs/view/innovation-lead-at-acme-1001?tracking=abc">
      </a>
      <h3 class="base-search-card__title">Innovation Lead</h3>
      <h4 class="base-search-card__subtitle">Acme Corp</h4>
      <span class="job-search-card__location">London, England, United Kingdom</span>
      <time class="job-search-card__listdate" datetime="2026-02-01"></time>
    </div>
  </li>
  <li>
    <div class="base-card base-card--link base-search-card job-search-card"
         data-entity-urn="urn:li:jobPosting:1002">
      <a class="base-card__full-link"
         href="https://uk.linkedin.com/jobs/view/remote-architect-at-globex-1002?tracking=xyz">
      </a>
      <h3 class="base-search-card__title">Enterprise Architect (Remote)</h3>
      <h4 class="base-search-card__subtitle">Globex</h4>
      <span class="job-search-card__location">Remote</span>
      <time class="job-search-card__listdate" datetime="2026-01-15"></time>
    </div>
  </li>
</ul>
"""


class TestLinkedInScraper:
    """Tests for LinkedIn scraper."""

    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        monkeypatch.setattr(
            "src.job_scrapers.linkedin_scraper.time.sleep", lambda _: None
        )

    def test_source_name(self, scraper):
        assert scraper._get_source_name() == "linkedin"

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_jobs_success(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)

        assert len(jobs) == 2
        assert jobs[0]["source_job_id"] == "1001"
        assert jobs[0]["title"] == "Innovation Lead"
        assert jobs[0]["company"] == "Acme Corp"
        assert jobs[0]["location"] == "London, England, United Kingdom"
        assert jobs[0]["remote"] is None

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_strips_tracking_params_from_url(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)

        assert "?tracking" not in jobs[0]["apply_url"]
        assert jobs[0]["apply_url"].endswith("1001")

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_detects_remote(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)

        assert jobs[1]["remote"] == "remote"

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_parses_date(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)

        assert isinstance(jobs[0]["posted_date"], datetime)
        assert jobs[0]["posted_date"].year == 2026
        assert jobs[0]["posted_date"].month == 2

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_deduplicates_across_terms(self, mock_get, scraper):
        """Same job returned by two search terms is only included once."""
        scraper.search_terms = ["innovation lead", "enterprise architect"]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)

        assert len(jobs) == 2  # not 4

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_stops_on_empty_page(self, mock_get, scraper):
        first = MagicMock()
        first.status_code = 200
        first.text = SAMPLE_LINKEDIN_HTML

        empty = MagicMock()
        empty.status_code = 200
        empty.text = "<ul></ul>"

        mock_get.side_effect = [first, empty]

        jobs = scraper._fetch_jobs(max_pages=3)
        assert len(jobs) == 2

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_rate_limit_returns_partial(self, mock_get, scraper):
        first = MagicMock()
        first.status_code = 200
        first.text = SAMPLE_LINKEDIN_HTML

        rate_limited = MagicMock()
        rate_limited.status_code = 429

        mock_get.side_effect = [first, rate_limited]

        jobs = scraper._fetch_jobs(max_pages=2)
        # Returns whatever was collected before the 429
        assert len(jobs) == 2

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_fetch_non_200_skips_term(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        jobs = scraper._fetch_jobs(max_pages=1)
        assert jobs == []

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_scrape_persists_jobs(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        jobs = scraper.scrape(max_retries=1)

        assert len(jobs) == 2
        saved = scraper.session.query(Job).filter(Job.source == "linkedin").all()
        assert len(saved) == 2

    @patch("src.job_scrapers.linkedin_scraper.requests.get")
    def test_scrape_deduplicates(self, mock_get, scraper):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_LINKEDIN_HTML
        mock_get.return_value = mock_response

        first = scraper.scrape(max_retries=1)
        second = scraper.scrape(max_retries=1)

        assert len(first) == 2
        assert len(second) == 0
        saved = scraper.session.query(Job).filter(Job.source == "linkedin").all()
        assert len(saved) == 2
