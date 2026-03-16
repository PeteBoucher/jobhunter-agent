"""Unit tests for ThoughtworksScraper."""

from unittest.mock import MagicMock, patch

import pytest

from src.job_scrapers.thoughtworks_scraper import _API_URL, ThoughtworksScraper


@pytest.fixture
def session():
    return MagicMock()


@pytest.fixture
def scraper(session):
    return ThoughtworksScraper(session)


SAMPLE_JOB = {
    "sourceSystemId": 7649020,
    "name": "Senior Developer",
    "role": "Developer",
    "location": "London",
    "country": "United Kingdom",
    "jobFunctions": ["Technology"],
    "remoteEligible": False,
    "updatedAt": "2026-03-15T15:48:14-04:00",
}

SAMPLE_REMOTE_JOB = {
    "sourceSystemId": 9999999,
    "name": "Principal Consultant",
    "role": "Consultant",
    "location": "",
    "country": "",
    "jobFunctions": ["Business"],
    "remoteEligible": True,
    "updatedAt": "2026-03-10T10:00:00+00:00",
}


def test_source_name(scraper):
    assert scraper._get_source_name() == "thoughtworks"


def test_fetch_jobs_calls_api(scraper):
    mock_response = MagicMock()
    mock_response.json.return_value = {"jobs": [SAMPLE_JOB]}

    with patch("requests.get", return_value=mock_response) as mock_get:
        jobs = scraper._fetch_jobs()

    mock_get.assert_called_once_with(_API_URL, timeout=15)
    assert len(jobs) == 1


def test_fetch_jobs_returns_empty_on_no_jobs(scraper):
    mock_response = MagicMock()
    mock_response.json.return_value = {}

    with patch("requests.get", return_value=mock_response):
        jobs = scraper._fetch_jobs()

    assert jobs == []


def test_parse_job_maps_fields(scraper):
    parsed = scraper._parse_job(SAMPLE_JOB)

    assert parsed["source_job_id"] == "7649020"
    assert parsed["title"] == "Senior Developer"
    assert parsed["company"] == "Thoughtworks"
    assert parsed["department"] == "Developer"
    assert parsed["location"] == "London"
    assert parsed["remote"] is None
    assert (
        parsed["apply_url"] == "https://www.thoughtworks.com/careers/jobs/job/7649020"
    )
    assert parsed["company_industry"] == "Technology Consulting"
    assert parsed["source_type"] == "company_portal"


def test_parse_job_remote_eligible(scraper):
    parsed = scraper._parse_job(SAMPLE_REMOTE_JOB)

    assert parsed["remote"] == "remote"


def test_parse_job_falls_back_to_country_when_no_location(scraper):
    job = {**SAMPLE_JOB, "location": "", "country": "Germany"}
    parsed = scraper._parse_job(job)
    assert parsed["location"] == "Germany"


def test_parse_job_handles_bad_date(scraper):
    from datetime import datetime

    job = {**SAMPLE_JOB, "updatedAt": "not-a-date"}
    parsed = scraper._parse_job(job)
    assert isinstance(parsed["posted_date"], datetime)


def test_thoughtworks_in_registry():
    from src.job_scrapers.registry import DEFAULT_SOURCES, SCRAPER_MAP

    assert "thoughtworks" in SCRAPER_MAP
    assert "thoughtworks" in DEFAULT_SOURCES
