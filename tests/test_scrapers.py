"""Tests for job scrapers."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.bamboohr_scraper import BambooHRScraper
from src.job_scrapers.base_scraper import BaseScraper
from src.job_scrapers.bcg_scraper import BCGScraper
from src.job_scrapers.github_scraper import GitHubJobsScraper
from src.job_scrapers.jobboardly_scraper import JobboardlyScraper
from src.job_scrapers.microsoft_scraper import MicrosoftScraper
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
        # Cleanup handled by context manager


@pytest.fixture
def session(temp_db):
    """Get database session."""
    session = get_session()
    yield session
    session.close()


@pytest.fixture
def github_scraper(session):
    """Create GitHub scraper instance."""
    return GitHubJobsScraper(session)


@pytest.fixture
def microsoft_scraper(session):
    """Create Microsoft scraper instance."""
    return MicrosoftScraper(session)


class TestBaseScraper:
    """Tests for BaseScraper abstract class."""

    def test_base_scraper_is_abstract(self, session):
        """Test that BaseScraper cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseScraper(session)

    def test_load_existing_ids_empty_for_new_source(self, github_scraper):
        """Test that _load_existing_ids returns empty set when no jobs exist."""
        result = github_scraper._load_existing_ids()
        assert result == set()

    def test_create_job_object(self, github_scraper):
        """Test creating a Job object from parsed data."""
        parsed_data = {
            "source_job_id": "job-123",
            "title": "Senior Python Engineer",
            "company": "Tech Company",
            "location": "San Francisco, CA",
            "remote": "remote",
            "description": "Build amazing software",
            "apply_url": "https://example.com/job/123",
            "posted_date": datetime.utcnow(),
            "source_type": "aggregator",
        }

        job = github_scraper._create_job_object(parsed_data)

        assert isinstance(job, Job)
        assert job.source == "github"
        assert job.source_job_id == "job-123"
        assert job.title == "Senior Python Engineer"
        assert job.company == "Tech Company"


class TestInferCountry:
    """Tests for BaseScraper._infer_country."""

    def test_us_state_enumeration(self):
        desc = (
            "This is a remote position, open to candidates who reside in: "
            "Arizona, California, Florida, Georgia, Illinois, Iowa, Kansas, "
            "Michigan, Missouri, Nebraska, New Jersey, New York, North Carolina, "
            "Ohio, Pennsylvania, South Carolina, Tennessee, Texas and Virginia."
        )
        assert BaseScraper._infer_country(desc) == "us"

    def test_fewer_than_threshold_states_returns_none(self):
        desc = "We have offices in California and Texas."
        assert BaseScraper._infer_country(desc) is None

    def test_us_only_explicit(self):
        assert BaseScraper._infer_country("This role is US-only.") == "us"
        assert BaseScraper._infer_country("US only applicants considered.") == "us"

    def test_reside_in_united_states(self):
        desc = "Candidates must reside in the United States to be eligible."
        assert BaseScraper._infer_country(desc) == "us"

    def test_uk_only(self):
        assert BaseScraper._infer_country("This position is UK-only.") == "gb"

    def test_reside_in_united_kingdom(self):
        desc = "You must be based in the United Kingdom."
        assert BaseScraper._infer_country(desc) == "gb"

    def test_location_field_us(self):
        assert BaseScraper._infer_country(None, "Remote, United States") == "us"
        assert BaseScraper._infer_country(None, "Remote (USA)") == "us"

    def test_location_field_gb(self):
        assert BaseScraper._infer_country(None, "Remote, United Kingdom") == "gb"

    def test_no_restriction_returns_none(self):
        desc = "We are a global company open to candidates everywhere."
        assert BaseScraper._infer_country(desc) is None

    def test_none_inputs(self):
        assert BaseScraper._infer_country(None) is None
        assert BaseScraper._infer_country(None, None) is None

    def test_create_job_object_infers_country(self, github_scraper):
        """_create_job_object sets country from description when not supplied."""
        parsed_data = {
            "source_job_id": "job-999",
            "title": "Engineer",
            "company": "Acme",
            "location": "Remote",
            "remote": "remote",
            "description": (
                "Open to candidates who reside in: Arizona, California, Texas, "
                "New York, Florida, Illinois, Ohio, Georgia, Michigan, Virginia."
            ),
            "apply_url": "https://example.com/apply",
            "posted_date": datetime.utcnow(),
            "source_type": "company_portal",
        }
        job = github_scraper._create_job_object(parsed_data)
        assert job.country == "us"


class TestGitHubJobsScraper:
    """Tests for GitHub Jobs scraper."""

    def test_source_name(self, github_scraper):
        """Test that GitHub scraper has correct source name."""
        assert github_scraper._get_source_name() == "github"

    def test_parse_github_job(self, github_scraper):
        """Test parsing a GitHub Jobs API response."""
        raw_job = {
            "id": "abc123",
            "title": "Senior Backend Engineer",
            "company": "GitHub",
            "location": "San Francisco, CA",
            "type": "Full Time",
            "description": "We are looking for Python and JavaScript developers",
            "url": "https://jobs.github.com/positions/abc123",
            "created_at": "2024-02-09T12:00:00Z",
        }

        parsed = github_scraper._parse_job(raw_job)

        assert parsed["source_job_id"] == "abc123"
        assert parsed["title"] == "Senior Backend Engineer"
        assert parsed["company"] == "GitHub"
        assert parsed["location"] == "San Francisco, CA"
        assert parsed["apply_url"] == "https://jobs.github.com/positions/abc123"
        assert "python" in parsed["requirements"]
        assert "javascript" in parsed["requirements"]

    def test_extract_requirements(self, github_scraper):
        """Test requirement extraction from description."""
        description = "We need Python, JavaScript, and Docker experience"
        requirements = github_scraper._extract_requirements(description)

        assert "python" in requirements
        assert "javascript" in requirements
        assert "docker" in requirements

    def test_fetch_github_jobs_success(self, github_scraper):
        """Test successful GitHub Jobs API fetch - deprecated API returns empty."""
        # GitHub Jobs API is deprecated; endpoint returns empty list
        jobs = github_scraper._fetch_jobs(description="python")

        assert len(jobs) == 0
        assert jobs == []

    def test_fetch_github_jobs_api_error(self, github_scraper):
        """Test GitHub Jobs API error handling - deprecated API no longer raises."""
        # GitHub Jobs API is deprecated; no longer makes requests or raises errors
        jobs = github_scraper._fetch_jobs()
        assert len(jobs) == 0

    def test_scrape_github_jobs(self, github_scraper):
        """Test GitHub Jobs scraping - returns empty due to API deprecation."""
        # GitHub Jobs API is deprecated; scrape returns empty list
        jobs = github_scraper.scrape()

        assert len(jobs) == 0

        # Verify no jobs are saved in database
        saved_jobs = (
            github_scraper.session.query(Job).filter(Job.source == "github").all()
        )
        assert len(saved_jobs) == 0


class TestMicrosoftScraper:
    """Tests for Microsoft careers scraper."""

    def test_source_name(self, microsoft_scraper):
        """Test that Microsoft scraper has correct source name."""
        assert microsoft_scraper._get_source_name() == "microsoft"

    def test_parse_microsoft_job(self, microsoft_scraper):
        """Test parsing a Microsoft API response."""
        raw_job = {
            "jobId": "12345",
            "title": "Cloud Solutions Architect",
            "category": "Engineering",
            "location": "Seattle, WA",
            "description": "Work with Azure, C#, and .NET",
            "postingDate": "2024-02-09T10:00:00Z",
        }

        parsed = microsoft_scraper._parse_job(raw_job)

        assert parsed["source_job_id"] == "12345"
        assert parsed["title"] == "Cloud Solutions Architect"
        assert parsed["company"] == "Microsoft"
        assert parsed["source_type"] == "company_portal"
        assert "azure" in parsed["requirements"]
        assert "c#" in parsed["requirements"]

    def test_extract_microsoft_requirements(self, microsoft_scraper):
        """Test requirement extraction for Microsoft jobs."""
        description = "Required: C#, .NET, Azure, SQL Server, REST API"
        requirements = microsoft_scraper._extract_requirements(description)

        assert "c#" in requirements
        assert ".net" in requirements
        assert "azure" in requirements
        assert "sql server" in requirements

    def test_fetch_microsoft_jobs_success(self, microsoft_scraper):
        """Test Microsoft API fetch - deprecated API returns empty."""
        # Microsoft API endpoint has changed; returns empty list
        jobs = microsoft_scraper._fetch_jobs(keywords="engineer")

        assert len(jobs) == 0
        assert jobs == []

    def test_fetch_microsoft_jobs_api_error(self, microsoft_scraper):
        """Test Microsoft API error handling - no longer makes requests."""
        # Microsoft API endpoint has changed; no longer makes requests
        jobs = microsoft_scraper._fetch_jobs()
        assert len(jobs) == 0

    def test_scrape_microsoft_jobs(self, microsoft_scraper):
        """Test Microsoft Jobs scraping - returns empty due to API changes."""
        # Microsoft API endpoint has changed; scrape returns empty list
        jobs = microsoft_scraper.scrape()

        assert len(jobs) == 0

        # Verify no jobs are saved
        saved_jobs = (
            microsoft_scraper.session.query(Job).filter(Job.source == "microsoft").all()
        )
        assert len(saved_jobs) == 0


class TestScraperIntegration:
    """Integration tests for scrapers."""

    def test_scrape_multiple_sources(self, session):
        """Test scraping multiple sources - both return empty."""
        # Both GitHub and Microsoft APIs have changed; both return empty lists
        github_scraper = GitHubJobsScraper(session)
        microsoft_scraper = MicrosoftScraper(session)

        github_jobs = github_scraper.scrape()
        microsoft_jobs = microsoft_scraper.scrape()

        assert len(github_jobs) == 0
        assert len(microsoft_jobs) == 0

        # Verify no jobs in database
        all_jobs = session.query(Job).all()
        assert len(all_jobs) == 0


# ---------------------------------------------------------------------------
# BCG scraper tests
# ---------------------------------------------------------------------------

_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://careers.bcg.com/global/en/job/11111/Software-Engineer</loc></url>
  <url><loc>https://careers.bcg.com/global/en/job/22222/Management-Consultant</loc></url>
  <url><loc>https://careers.bcg.com/global/en/</loc></url>
</urlset>
"""

_TECH_JOB_HTML = (
    "<html><head>"
    '<meta property="og:title" content="Software Engineer in London, UK'
    ' | Technology and Engineering at BCG">'
    '<meta property="og:url" content="https://careers.bcg.com/global/en'
    '/job/11111/Software-Engineer">'
    "</head><body></body></html>"
)

_OTHER_JOB_HTML = (
    "<html><head>"
    '<meta property="og:title" content="Management Consultant in New York,'
    ' USA | Consulting at BCG">'
    '<meta property="og:url" content="https://careers.bcg.com/global/en'
    '/job/22222/Management-Consultant">'
    "</head><body></body></html>"
)


@pytest.fixture
def bcg_scraper(session):
    return BCGScraper(session)


class TestBCGScraper:
    def test_jobs_from_sitemaps_extracts_ids(self, bcg_scraper):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.text = _SITEMAP_XML

        with patch.object(bcg_scraper._http, "get", return_value=mock_resp):
            pairs = bcg_scraper._jobs_from_sitemaps()

        ids = [p[0] for p in pairs]
        assert "11111" in ids
        assert "22222" in ids
        # Non-job URL must not appear
        assert (
            len([p for p in pairs if "/en/" == p[1].rstrip("/").split("/global")[1]])
            == 0
        )

    def test_fetch_job_meta_parses_og_tags(self, bcg_scraper):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _TECH_JOB_HTML

        with patch.object(bcg_scraper._http, "get", return_value=mock_resp):
            job = bcg_scraper._fetch_job_meta(
                "11111", "https://careers.bcg.com/global/en/job/11111/Software-Engineer"
            )

        assert job["source_job_id"] == "11111"
        assert job["title"] == "Software Engineer"
        assert job["location"] == "London, UK"
        assert job["department"] == "Technology and Engineering"
        assert job["company"] == "BCG"
        assert (
            job["apply_url"]
            == "https://careers.bcg.com/global/en/job/11111/Software-Engineer"
        )

    def test_fetch_jobs_returns_all_departments(self, bcg_scraper):
        """All departments are returned so every job ID gets stored on first run."""
        sitemap_resp = MagicMock()
        sitemap_resp.raise_for_status.return_value = None
        sitemap_resp.text = _SITEMAP_XML

        tech_resp = MagicMock()
        tech_resp.status_code = 200
        tech_resp.text = _TECH_JOB_HTML

        other_resp = MagicMock()
        other_resp.status_code = 200
        other_resp.text = _OTHER_JOB_HTML

        def get_side_effect(url, **kwargs):
            if "sitemap" in url:
                return sitemap_resp
            if "11111" in url:
                return tech_resp
            return other_resp

        with patch.object(bcg_scraper._http, "get", side_effect=get_side_effect):
            with patch("time.sleep"):
                jobs = bcg_scraper._fetch_jobs()

        assert len(jobs) == 2
        source_ids = {j["source_job_id"] for j in jobs}
        assert "11111" in source_ids
        assert "22222" in source_ids

    def test_parse_job_is_passthrough(self, bcg_scraper):
        raw = {"source_job_id": "99", "title": "Tester", "company": "BCG"}
        assert bcg_scraper._parse_job(raw) is raw

    def test_fetch_job_meta_404_returns_none(self, bcg_scraper):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch.object(bcg_scraper._http, "get", return_value=mock_resp):
            result = bcg_scraper._fetch_job_meta(
                "99", "https://careers.bcg.com/global/en/job/99/Gone"
            )

        assert result is None


# ---------------------------------------------------------------------------
# BambooHR scraper tests
# ---------------------------------------------------------------------------

_BAMBOO_LIST_RESP = {
    "meta": {"totalCount": 2},
    "result": [
        {
            "id": "176",
            "jobOpeningName": "Senior SDET",
            "departmentId": "123",
            "departmentLabel": "Technology",
            "employmentStatusLabel": "Permanent",
            "location": {"city": None, "state": None},
            "isRemote": None,
            "locationType": "1",
        },
        {
            "id": "117",
            "jobOpeningName": "Don't see a role? Join our Talent Pool",
            "departmentId": None,
            "departmentLabel": None,
            "employmentStatusLabel": "Permanent",
            "location": {"city": None, "state": None},
            "isRemote": None,
            "locationType": "1",
        },
    ],
}

_BAMBOO_DETAIL_RESP = {
    "meta": {},
    "result": {
        "jobOpening": {
            "jobOpeningName": "Senior SDET",
            "locationType": "1",
            "location": {"city": None, "state": None, "addressCountry": None},
            "atsLocation": {
                "country": "United Kingdom",
                "countryId": "222",
                "state": None,
                "city": None,
            },
            "description": "<p>Build great test frameworks.</p>",
            "datePosted": "2026-06-03",
        }
    },
}


@pytest.fixture
def bamboohr_scraper(session):
    return BambooHRScraper(session, company_slugs=["semble"])


class TestBambooHRScraper:
    def test_source_name(self, bamboohr_scraper):
        assert bamboohr_scraper._get_source_name() == "bamboohr"

    def test_fetch_jobs_skips_talent_pool(self, bamboohr_scraper):
        list_resp = MagicMock()
        list_resp.raise_for_status.return_value = None
        list_resp.json.return_value = _BAMBOO_LIST_RESP

        detail_resp = MagicMock()
        detail_resp.status_code = 200
        detail_resp.json.return_value = _BAMBOO_DETAIL_RESP

        def get_side_effect(url, **kwargs):
            if url.endswith("/list"):
                return list_resp
            return detail_resp

        with patch.object(bamboohr_scraper._http, "get", side_effect=get_side_effect):
            with patch("time.sleep"):
                jobs = bamboohr_scraper._fetch_jobs()

        # Only the "Senior SDET" job — talent pool entry is filtered out
        assert len(jobs) == 1
        assert jobs[0]["_source_job_id"] == "semble-176"

    def test_parse_job_remote_and_country(self, bamboohr_scraper):
        raw = {
            "_slug": "semble",
            "_source_job_id": "semble-176",
            "id": "176",
            "jobOpeningName": "Senior SDET",
            "departmentLabel": "Technology",
            "location": {"city": None, "state": None},
            "locationType": "1",
            "_detail": {
                "location": {"addressCountry": None},
                "atsLocation": {
                    "country": "United Kingdom",
                    "state": None,
                    "city": None,
                },
                "description": "<p>Build great test frameworks.</p>",
                "datePosted": "2026-06-03",
            },
        }
        parsed = bamboohr_scraper._parse_job(raw)

        assert parsed["source_job_id"] == "semble-176"
        assert parsed["title"] == "Senior SDET"
        assert parsed["company"] == "Semble"
        assert parsed["remote"] == "remote"
        assert parsed["country"] == "gb"
        assert parsed["department"] == "Technology"
        assert "Build great test frameworks" in parsed["description"]
        assert parsed["apply_url"] == "https://semble.bamboohr.com/careers/176"

    def test_parse_job_hybrid_location_type(self, bamboohr_scraper):
        raw = {
            "_slug": "semble",
            "_source_job_id": "semble-180",
            "id": "180",
            "jobOpeningName": "Delivery Manager",
            "departmentLabel": "Technology",
            "location": {"city": "London", "state": None},
            "locationType": "2",
            "_detail": {},
        }
        parsed = bamboohr_scraper._parse_job(raw)
        assert parsed["remote"] == "hybrid"
        assert parsed["location"] == "London"

    def test_parse_job_company_name_from_map(self, bamboohr_scraper):
        raw = {
            "_slug": "semble",
            "_source_job_id": "semble-1",
            "id": "1",
            "jobOpeningName": "Engineer",
            "departmentLabel": None,
            "location": {"city": None, "state": None},
            "locationType": "0",
            "_detail": {},
        }
        assert bamboohr_scraper._parse_job(raw)["company"] == "Semble"

    def test_fetch_detail_404_returns_empty(self, bamboohr_scraper):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch.object(bamboohr_scraper._http, "get", return_value=mock_resp):
            result = bamboohr_scraper._fetch_detail("semble", "999")
        assert result == {}


# ── Jobboardly scraper ────────────────────────────────────────────────────────

_JOBBOARDLY_RAW = {
    "_board_subdomain": "iglubit-1",
    "links": {"self": "/jobs/senior-engineer-abc123"},
    "title": "Senior Engineer",
    "location": "onsite",
    "company": {"name": "Acme", "logo": "", "location": "Sevilla, Spain"},
    "location_limits": ["ES"],
    "description": {"html": "<p>Great role</p>", "text": "Great role"},
    "salary": {"schedule": "yearly", "minimum": None, "maximum": None},
    "application_link": "https://acme.com/apply/123",
    "published_at": "2026-08-01T00:00:00Z",
}


@pytest.fixture
def jobboardly_scraper(session):
    return JobboardlyScraper(session)


class TestJobboardlyScraper:
    def test_salary_cents_dict_converted_to_float(self, jobboardly_scraper):
        """salary min/max cents dicts must be converted to float, not passed to DB."""
        raw = {
            **_JOBBOARDLY_RAW,
            "salary": {
                "schedule": "yearly",
                "minimum": {"cents": 4190000, "currency_iso": "EUR"},
                "maximum": {"cents": 6702500, "currency_iso": "EUR"},
            },
        }
        parsed = jobboardly_scraper._parse_job(raw)
        assert parsed["salary_min"] == 41900.0
        assert parsed["salary_max"] == 67025.0
        assert isinstance(parsed["salary_min"], float)

    def test_salary_none_stays_none(self, jobboardly_scraper):
        """Null salary fields must remain None, not raise."""
        parsed = jobboardly_scraper._parse_job(_JOBBOARDLY_RAW)
        assert parsed["salary_min"] is None
        assert parsed["salary_max"] is None

    def test_remote_onsite_is_none_string(self, jobboardly_scraper):
        """An onsite job must produce remote=None, not False."""
        parsed = jobboardly_scraper._parse_job(_JOBBOARDLY_RAW)
        assert parsed["remote"] is None
        assert not isinstance(parsed["remote"], bool)

    def test_remote_flag_is_string(self, jobboardly_scraper):
        """A remote job must produce remote='remote', not True."""
        raw = {**_JOBBOARDLY_RAW, "location": "remote"}
        parsed = jobboardly_scraper._parse_job(raw)
        assert parsed["remote"] == "remote"
        assert not isinstance(parsed["remote"], bool)

    def test_worldwide_location_limit_becomes_none(self, jobboardly_scraper):
        """'Worldwide' in location_limits must not be stored as country."""
        raw = {**_JOBBOARDLY_RAW, "location_limits": ["Worldwide"]}
        parsed = jobboardly_scraper._parse_job(raw)
        assert parsed["country"] is None

    def test_iso2_location_limit_stored_lowercase(self, jobboardly_scraper):
        """Valid ISO2 location limit is stored as lowercase."""
        parsed = jobboardly_scraper._parse_job(_JOBBOARDLY_RAW)
        assert parsed["country"] == "es"

    def test_empty_location_limits_gives_none_country(self, jobboardly_scraper):
        """No location_limits means country is None (base class will infer)."""
        raw = {**_JOBBOARDLY_RAW, "location_limits": []}
        parsed = jobboardly_scraper._parse_job(raw)
        assert parsed["country"] is None

    def test_source_job_id_combines_subdomain_and_slug(self, jobboardly_scraper):
        parsed = jobboardly_scraper._parse_job(_JOBBOARDLY_RAW)
        assert parsed["source_job_id"] == "iglubit-1:senior-engineer-abc123"
