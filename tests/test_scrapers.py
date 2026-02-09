"""Tests for job scrapers."""

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.base_scraper import BaseScraper
from src.job_scrapers.github_scraper import GitHubJobsScraper
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

    def test_job_exists_returns_none_for_new_job(self, github_scraper):
        """Test that _job_exists returns None for non-existent job."""
        parsed_data = {
            "source_job_id": "job-123",
            "title": "Test Job",
            "company": "Test Company",
        }
        result = github_scraper._job_exists(parsed_data)
        assert result is None

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

    @patch("requests.get")
    def test_fetch_github_jobs_success(self, mock_get, github_scraper):
        """Test successful GitHub Jobs API fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "job1",
                "title": "Python Developer",
                "company": "Company A",
                "location": "Remote",
                "description": "Python role",
                "url": "https://example.com",
                "type": "Full Time",
            }
        ]
        mock_get.return_value = mock_response

        jobs = github_scraper._fetch_jobs(description="python")

        assert len(jobs) == 1
        assert jobs[0]["title"] == "Python Developer"
        mock_get.assert_called_once()

    @patch("src.job_scrapers.github_scraper.requests.get")
    def test_fetch_github_jobs_api_error(self, mock_get, github_scraper):
        """Test GitHub Jobs API error handling."""
        import requests

        mock_get.side_effect = requests.RequestException("Connection error")

        with pytest.raises(RuntimeError):
            github_scraper._fetch_jobs()

    @patch("requests.get")
    def test_scrape_github_jobs(self, mock_get, github_scraper):
        """Test complete GitHub Jobs scraping workflow."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "job1",
                "title": "Python Developer",
                "company": "Company A",
                "location": "Remote",
                "description": "Python and Django",
                "url": "https://example.com/job1",
                "type": "Full Time",
                "created_at": "2024-02-09T12:00:00Z",
            },
            {
                "id": "job2",
                "title": "JavaScript Engineer",
                "company": "Company B",
                "location": "New York, NY",
                "description": "React and Node.js",
                "url": "https://example.com/job2",
                "type": "Full Time",
                "created_at": "2024-02-09T11:00:00Z",
            },
        ]
        mock_get.return_value = mock_response

        jobs = github_scraper.scrape()

        assert len(jobs) == 2
        assert jobs[0].title == "Python Developer"
        assert jobs[1].title == "JavaScript Engineer"

        # Verify jobs are saved in database
        saved_jobs = (
            github_scraper.session.query(Job).filter(Job.source == "github").all()
        )
        assert len(saved_jobs) == 2


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

    @patch("requests.get")
    def test_fetch_microsoft_jobs_success(self, mock_get, microsoft_scraper):
        """Test successful Microsoft API fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "operationResult": {
                "result": {
                    "jobs": [
                        {
                            "jobId": "ms1",
                            "title": "Software Engineer",
                            "category": "Engineering",
                            "location": "Redmond, WA",
                            "description": "C# and .NET",
                        }
                    ]
                }
            }
        }
        mock_get.return_value = mock_response

        jobs = microsoft_scraper._fetch_jobs(keywords="engineer")

        assert len(jobs) == 1
        assert jobs[0]["title"] == "Software Engineer"

    @patch("src.job_scrapers.microsoft_scraper.requests.get")
    def test_fetch_microsoft_jobs_api_error(self, mock_get, microsoft_scraper):
        """Test Microsoft API error handling."""
        import requests

        mock_get.side_effect = requests.RequestException("Connection timeout")

        with pytest.raises(RuntimeError):
            microsoft_scraper._fetch_jobs()

    @patch("requests.get")
    def test_scrape_microsoft_jobs(self, mock_get, microsoft_scraper):
        """Test complete Microsoft Jobs scraping workflow."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "operationResult": {
                "result": {
                    "jobs": [
                        {
                            "jobId": "ms1",
                            "title": "Senior Engineer",
                            "category": "Engineering",
                            "location": "Seattle, WA",
                            "description": "C# and Azure",
                            "postingDate": "2024-02-09T10:00:00Z",
                        },
                        {
                            "jobId": "ms2",
                            "title": "Product Manager",
                            "category": "Product",
                            "location": "Remote",
                            "description": "Azure and cloud services",
                            "postingDate": "2024-02-09T09:00:00Z",
                        },
                    ]
                }
            }
        }
        mock_get.return_value = mock_response

        jobs = microsoft_scraper.scrape()

        assert len(jobs) == 2
        assert jobs[0].title == "Senior Engineer"
        assert jobs[1].title == "Product Manager"

        # Verify jobs are saved
        saved_jobs = (
            microsoft_scraper.session.query(Job).filter(Job.source == "microsoft").all()
        )
        assert len(saved_jobs) == 2


class TestScraperIntegration:
    """Integration tests for scrapers."""

    @patch("requests.get")
    def test_scrape_multiple_sources(self, mock_get, session):
        """Test scraping from multiple sources in one workflow."""
        # Setup GitHub response
        github_response = MagicMock()
        github_response.json.return_value = [
            {
                "id": "gh1",
                "title": "Python Dev",
                "company": "GH Co",
                "location": "Remote",
                "description": "Python",
                "url": "https://github.com/job",
                "type": "Full Time",
                "created_at": "2024-02-09T12:00:00Z",
            }
        ]

        # Setup Microsoft response
        microsoft_response = MagicMock()
        microsoft_response.json.return_value = {
            "operationResult": {
                "result": {
                    "jobs": [
                        {
                            "jobId": "ms1",
                            "title": "C# Developer",
                            "category": "Engineering",
                            "location": "Seattle, WA",
                            "description": "C# role",
                            "postingDate": "2024-02-09T10:00:00Z",
                        }
                    ]
                }
            }
        }

        # Mock both requests
        mock_get.side_effect = [github_response, microsoft_response]

        github_scraper = GitHubJobsScraper(session)
        microsoft_scraper = MicrosoftScraper(session)

        github_jobs = github_scraper.scrape()
        microsoft_jobs = microsoft_scraper.scrape()

        assert len(github_jobs) == 1
        assert len(microsoft_jobs) == 1

        # Verify all jobs in database
        all_jobs = session.query(Job).all()
        assert len(all_jobs) == 2
        assert any(j.source == "github" for j in all_jobs)
        assert any(j.source == "microsoft" for j in all_jobs)
