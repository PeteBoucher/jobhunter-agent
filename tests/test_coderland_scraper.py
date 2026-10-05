"""Tests for the Coderland (Manatal) scraper."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import requests

from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.coderland_scraper import (
    CODERLAND_API,
    CodelandScraper,
    _strip_html,
)


def _scraper():
    scraper = CodelandScraper(MagicMock())
    scraper._http = MagicMock()
    return scraper


def _raw(**overrides):
    raw = {
        "id": 4821,
        "title": "Senior Python Developer",
        "description": "<p>Build <b>APIs</b> for our clients.</p>",
        "mode": "Remote",
        "technologies": ["Python", "Django", "AWS"],
        "requires": ["<p>5+ years of Python</p>", "", "Advanced English"],
        "responsibilities": "<p>Build APIs for our clients.</p>",
    }
    raw.update(overrides)
    return raw


def test_strip_html():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_fetch_jobs_requests_everything_in_one_page():
    scraper = _scraper()
    scraper._http.get.return_value.json.return_value = {
        "data": [{"id": 1}, {"id": 2}],
        "hasNextPage": True,
    }

    jobs = scraper._fetch_jobs()

    assert jobs == [{"id": 1}, {"id": 2}]
    scraper._http.get.assert_called_once_with(
        CODERLAND_API, params={"language": "en", "perPage": "200"}, timeout=15
    )


def test_fetch_jobs_returns_empty_on_error_or_missing_data():
    scraper = _scraper()
    scraper._http.get.side_effect = requests.ConnectionError("down")
    assert scraper._fetch_jobs() == []

    scraper._http.get.side_effect = None
    scraper._http.get.return_value.json.return_value = {}
    assert scraper._fetch_jobs() == []


def test_parse_job_matches_schema():
    parsed = _scraper()._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "4821"
    assert parsed["title"] == "Senior Python Developer"
    assert parsed["company"] == "Coderland"
    assert parsed["remote"] == "remote"
    assert parsed["description"] == "Build APIs for our clients."
    assert parsed["requirements"] == "5+ years of Python; Advanced English"
    assert parsed["nice_to_haves"] == "Python, Django, AWS"
    assert parsed["apply_url"] == "https://www.coderland.com/en/work-us/4821"
    assert isinstance(parsed["posted_date"], datetime)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("Remote", "remote"),
        ("HYBRID", "hybrid"),
        ("Hybrid / Remote", "hybrid"),
        ("On-site", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_job_mode(mode, expected):
    assert _scraper()._parse_job(_raw(mode=mode))["remote"] == expected


def test_parse_job_optional_fields_absent():
    parsed = _scraper()._parse_job(
        _raw(description=None, requires=None, technologies=None)
    )

    assert validate_parsed_job(parsed) == []
    assert parsed["description"] is None
    assert parsed["requirements"] is None
    assert parsed["nice_to_haves"] is None


def test_parse_job_title_falls_back_to_position():
    parsed = _scraper()._parse_job(_raw(title=None, position="QA Engineer"))
    assert parsed["title"] == "QA Engineer"


def test_parse_job_truncates_description():
    parsed = _scraper()._parse_job(_raw(description="<p>" + "x" * 6000 + "</p>"))
    assert len(parsed["description"]) == 5000
