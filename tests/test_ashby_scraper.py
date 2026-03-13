"""Unit tests for AshbyScraper."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.job_scrapers.ashby_scraper import AshbyScraper


@pytest.fixture
def session():
    return MagicMock()


@pytest.fixture
def scraper(session):
    return AshbyScraper(session, board_slugs=["acme", "test-co"])


# ---------------------------------------------------------------------------
# basic setup
# ---------------------------------------------------------------------------


def test_source_name(scraper):
    assert scraper._get_source_name() == "ashby"


def test_custom_board_slugs(session):
    s = AshbyScraper(session, board_slugs=["foo", "bar"])
    assert s.board_slugs == ["foo", "bar"]


def test_default_board_slugs_used_when_none(session):
    from src.job_scrapers.ashby_scraper import DEFAULT_BOARD_SLUGS

    s = AshbyScraper(session)
    assert s.board_slugs == DEFAULT_BOARD_SLUGS


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags():
    assert AshbyScraper._strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_collapses_whitespace():
    result = AshbyScraper._strip_html("<p>line1</p>   <p>line2</p>")
    assert "  " not in result
    assert "line1" in result
    assert "line2" in result


def test_strip_html_empty_string():
    assert AshbyScraper._strip_html("") == ""


def test_strip_html_none_returns_empty():
    assert AshbyScraper._strip_html(None) == ""


# ---------------------------------------------------------------------------
# _fetch_jobs
# ---------------------------------------------------------------------------


def _make_response(status_code: int, json_data: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    return resp


def test_fetch_jobs_success(scraper):
    job = {"id": "j1", "title": "Engineer", "isListed": True}
    responses = [
        _make_response(200, {"jobs": [job]}),
        _make_response(200, {"jobs": []}),
    ]
    with patch("requests.get", side_effect=responses):
        jobs = scraper._fetch_jobs()

    assert len(jobs) == 1
    assert jobs[0]["_board_slug"] == "acme"


def test_fetch_jobs_skips_unlisted(scraper):
    jobs = [
        {"id": "j1", "title": "Listed", "isListed": True},
        {"id": "j2", "title": "Unlisted", "isListed": False},
    ]
    responses = [
        _make_response(200, {"jobs": jobs}),
        _make_response(200, {"jobs": []}),
    ]
    with patch("requests.get", side_effect=responses):
        result = scraper._fetch_jobs()

    assert len(result) == 1
    assert result[0]["title"] == "Listed"


def test_fetch_jobs_404_skips_board(scraper):
    responses = [
        _make_response(404, {}),
        _make_response(200, {"jobs": [{"id": "j2", "isListed": True}]}),
    ]
    with patch("requests.get", side_effect=responses):
        result = scraper._fetch_jobs()

    assert len(result) == 1
    assert result[0]["_board_slug"] == "test-co"


def test_fetch_jobs_non_200_skips_board(scraper):
    responses = [
        _make_response(500, {}),
        _make_response(200, {"jobs": [{"id": "j2", "isListed": True}]}),
    ]
    with patch("requests.get", side_effect=responses):
        result = scraper._fetch_jobs()

    assert len(result) == 1


def test_fetch_jobs_request_exception_skips_board(scraper):
    with patch(
        "requests.get",
        side_effect=[
            requests.RequestException("timeout"),
            _make_response(200, {"jobs": []}),
        ],
    ):
        result = scraper._fetch_jobs()

    assert result == []


def test_fetch_jobs_board_slugs_override(scraper):
    with patch(
        "requests.get", return_value=_make_response(200, {"jobs": []})
    ) as mock_get:
        scraper._fetch_jobs(board_slugs=["override"])

    mock_get.assert_called_once()
    assert "override" in mock_get.call_args[0][0]


# ---------------------------------------------------------------------------
# _parse_job
# ---------------------------------------------------------------------------


def _raw(overrides: dict | None = None):
    base = {
        "_board_slug": "acme",
        "id": "abc123",
        "title": "Software Engineer",
        "location": "London, UK",
        "workplaceType": "",
        "isRemote": False,
        "descriptionPlain": "Build great things.",
        "publishedAt": "2024-01-15T12:00:00Z",
        "applyUrl": "https://jobs.ashbyhq.com/acme/abc123",
        "department": "Engineering",
    }
    if overrides:
        base.update(overrides)
    return base


def test_parse_job_basic_fields(scraper):
    parsed = scraper._parse_job(_raw())
    assert parsed["title"] == "Software Engineer"
    assert parsed["company"] == "Acme"  # slug "acme" → title-case
    assert parsed["location"] == "London, UK"
    assert parsed["description"] == "Build great things."
    assert parsed["apply_url"] == "https://jobs.ashbyhq.com/acme/abc123"
    assert parsed["source_job_id"] == "abc123"


def test_parse_job_company_name_from_slug(scraper):
    parsed = scraper._parse_job(_raw({"_board_slug": "runway-ml"}))
    assert parsed["company"] == "Runway Ml"


def test_parse_job_remote_from_workplace_type(scraper):
    parsed = scraper._parse_job(_raw({"workplaceType": "Remote"}))
    assert parsed["remote"] == "remote"


def test_parse_job_hybrid_from_workplace_type(scraper):
    parsed = scraper._parse_job(_raw({"workplaceType": "Hybrid"}))
    assert parsed["remote"] == "hybrid"


def test_parse_job_remote_from_is_remote_flag(scraper):
    parsed = scraper._parse_job(_raw({"workplaceType": "", "isRemote": True}))
    assert parsed["remote"] == "remote"


def test_parse_job_hybrid_from_location(scraper):
    parsed = scraper._parse_job(
        _raw({"workplaceType": "", "isRemote": False, "location": "London (Hybrid)"})
    )
    assert parsed["remote"] == "hybrid"


def test_parse_job_remote_from_location(scraper):
    parsed = scraper._parse_job(
        _raw({"workplaceType": "", "isRemote": False, "location": "Remote - Europe"})
    )
    assert parsed["remote"] == "remote"


def test_parse_job_onsite_no_remote(scraper):
    parsed = scraper._parse_job(
        _raw({"workplaceType": "", "isRemote": False, "location": "Berlin"})
    )
    assert parsed["remote"] is None


def test_parse_job_workplace_type_takes_precedence_over_is_remote(scraper):
    """workplaceType='Hybrid' overrides isRemote=True."""
    parsed = scraper._parse_job(_raw({"workplaceType": "Hybrid", "isRemote": True}))
    assert parsed["remote"] == "hybrid"


def test_parse_job_uses_html_description_fallback(scraper):
    raw = _raw({"descriptionPlain": "", "descriptionHtml": "<p>Hello <b>world</b></p>"})
    parsed = scraper._parse_job(raw)
    assert "Hello" in parsed["description"]
    assert "<p>" not in parsed["description"]


def test_parse_job_description_truncated_at_5000(scraper):
    long_desc = "x" * 6000
    parsed = scraper._parse_job(_raw({"descriptionPlain": long_desc}))
    assert len(parsed["description"]) == 5000


def test_parse_job_published_date_parsed(scraper):
    parsed = scraper._parse_job(_raw({"publishedAt": "2024-06-01T10:00:00Z"}))
    assert parsed["posted_date"].year == 2024
    assert parsed["posted_date"].month == 6


def test_parse_job_invalid_date_falls_back_to_now(scraper):
    parsed = scraper._parse_job(_raw({"publishedAt": "not-a-date"}))
    assert isinstance(parsed["posted_date"], datetime)


def test_parse_job_department_fallback_to_team(scraper):
    raw = _raw({"department": None, "team": "Product"})
    parsed = scraper._parse_job(raw)
    assert parsed["department"] == "Product"


def test_parse_job_apply_url_fallback_to_job_url(scraper):
    raw = _raw({"applyUrl": None, "jobUrl": "https://example.com/job/1"})
    parsed = scraper._parse_job(raw)
    assert parsed["apply_url"] == "https://example.com/job/1"


def test_parse_job_salary_always_none(scraper):
    parsed = scraper._parse_job(_raw())
    assert parsed["salary_min"] is None
    assert parsed["salary_max"] is None
