"""Tests for the SmartRecruiters scraper."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import requests

from src.job_matcher import _requirement_items
from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.smartrecruiters_scraper import (
    MAX_JOBS_PER_COMPANY,
    PAGE_SIZE,
    SR_API_BASE,
    SmartRecruitersScraper,
    _html_to_text,
)

DETAIL = {
    "applyUrl": "https://jobs.smartrecruiters.com/Playtech/123-apply",
    "postingUrl": "https://jobs.smartrecruiters.com/Playtech/123",
    "jobAd": {
        "sections": {
            "jobDescription": {"text": "<p>We build <b>games</b>.</p>"},
            "qualifications": {
                "text": "<ul><li>5 years of Python</li><li>Strong SQL</li>"
                "<li>Kubernetes in production</li></ul>"
            },
        }
    },
}


def _scraper(companies=None):
    scraper = SmartRecruitersScraper(
        MagicMock(), companies=companies or {"Playtech": "Playtech Ltd"}
    )
    scraper._http = MagicMock()
    return scraper


def _raw(**overrides):
    raw = {
        "id": "123",
        "name": "  Backend Engineer ",
        "ref": "https://api.smartrecruiters.com/v1/companies/Playtech/postings/123",
        "location": {"city": "Tallinn", "country": "ee", "remote": False},
        "department": {"label": "Engineering"},
        "releasedDate": "2026-08-20T10:00:00.000Z",
        "_company_id": "Playtech",
        "_source_job_id": "Playtech:123",
        "_detail": DETAIL,
    }
    raw.update(overrides)
    return raw


def _page(content, total):
    resp = MagicMock()
    resp.json.return_value = {"content": content, "totalFound": total}
    return resp


def test_html_to_text_keeps_list_items_on_separate_lines():
    text = _html_to_text("<ul><li>One</li><li>Two</li></ul>")
    assert text.split("\n") == ["One", "Two"]
    assert _html_to_text("") == ""


def test_parse_job_matches_schema():
    parsed = _scraper()._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "Playtech:123"
    assert parsed["title"] == "Backend Engineer"
    assert parsed["company"] == "Playtech Ltd"
    assert parsed["department"] == "Engineering"
    assert parsed["location"] == "Tallinn"
    assert parsed["country"] == "ee"
    assert parsed["remote"] is None
    assert parsed["description"].split() == ["We", "build", "games", "."]
    assert parsed["apply_url"] == DETAIL["applyUrl"]
    assert parsed["posted_date"].replace(tzinfo=None) == datetime(2026, 8, 20, 10, 0)


def test_requirements_score_as_separate_items():
    # SmartRecruiters stores `requirements` as one string; it must still
    # split into one phrase per qualification for job_matcher.
    parsed = _scraper()._parse_job(_raw())
    assert _requirement_items(parsed["requirements"]) == [
        "5 years of Python",
        "Strong SQL",
        "Kubernetes in production",
    ]


def test_parse_job_remote_and_hybrid_flags():
    scraper = _scraper()
    assert scraper._parse_job(_raw(location={"remote": True}))["remote"] == "remote"
    assert scraper._parse_job(_raw(location={"hybrid": True}))["remote"] == "hybrid"
    both = scraper._parse_job(_raw(location={"remote": True, "hybrid": True}))
    assert both["remote"] == "remote"


def test_parse_job_without_detail_falls_back_to_ref():
    # Already-known jobs skip the detail fetch (`_detail` is {}).
    parsed = _scraper()._parse_job(_raw(_detail={}))

    assert validate_parsed_job(parsed) == []
    assert parsed["description"] is None
    assert parsed["requirements"] is None
    assert parsed["apply_url"] == _raw()["ref"]


def test_parse_job_apply_url_prefers_posting_url_over_ref():
    detail = {"postingUrl": "https://jobs.smartrecruiters.com/Playtech/123"}
    assert _scraper()._parse_job(_raw(_detail=detail))["apply_url"] == (
        "https://jobs.smartrecruiters.com/Playtech/123"
    )


def test_parse_job_unknown_company_uses_id_and_bad_date_falls_back():
    parsed = _scraper()._parse_job(
        _raw(_company_id="Unknown", releasedDate="garbage", location=None)
    )
    assert parsed["company"] == "Unknown"
    assert isinstance(parsed["posted_date"], datetime)
    assert parsed["location"] is None
    assert parsed["country"] is None


def test_parse_job_truncates_long_text():
    detail = {
        "applyUrl": "https://x",
        "jobAd": {
            "sections": {
                "jobDescription": {"text": "d" * 6000},
                "qualifications": {"text": "q" * 3000},
            }
        },
    }
    parsed = _scraper()._parse_job(_raw(_detail=detail))
    assert len(parsed["description"]) == 5000
    assert len(parsed["requirements"]) == 2000


def test_fetch_company_listings_paginates():
    scraper = _scraper()
    scraper._http.get.side_effect = [
        _page([{"id": str(i)} for i in range(PAGE_SIZE)], total=PAGE_SIZE + 3),
        _page([{"id": "a"}, {"id": "b"}, {"id": "c"}], total=PAGE_SIZE + 3),
    ]

    listings = scraper._fetch_company_listings("Playtech")

    assert len(listings) == PAGE_SIZE + 3
    assert all(job["_company_id"] == "Playtech" for job in listings)
    calls = scraper._http.get.call_args_list
    assert calls[0].args[0] == f"{SR_API_BASE}/Playtech/postings"
    assert [c.kwargs["params"]["offset"] for c in calls] == [0, PAGE_SIZE]


def test_fetch_company_listings_caps_at_max_jobs():
    scraper = _scraper()
    scraper._http.get.side_effect = lambda *a, **kw: _page(
        [{"id": "x"} for _ in range(PAGE_SIZE)], total=10_000
    )
    listings = scraper._fetch_company_listings("Playtech")
    assert len(listings) == MAX_JOBS_PER_COMPANY


def test_fetch_company_listings_returns_partial_on_error():
    scraper = _scraper()
    scraper._http.get.side_effect = requests.ConnectionError("down")
    assert scraper._fetch_company_listings("Playtech") == []


def test_fetch_detail_non_200_and_error_return_empty():
    scraper = _scraper()
    scraper._http.get.return_value.status_code = 404
    assert scraper._fetch_detail("Playtech", "1") == {}
    scraper._http.get.side_effect = requests.ConnectionError("down")
    assert scraper._fetch_detail("Playtech", "1") == {}


@patch("src.job_scrapers.smartrecruiters_scraper.time.sleep")
def test_fetch_jobs_fetches_detail_only_for_new_jobs(_sleep):
    scraper = _scraper()
    scraper._load_existing_ids = MagicMock(return_value={"Playtech:1"})
    scraper._load_db_config = MagicMock(return_value=[])
    scraper._fetch_company_listings = MagicMock(return_value=[{"id": "1"}, {"id": "2"}])
    scraper._fetch_detail = MagicMock(return_value=DETAIL)

    raw = scraper._fetch_jobs()

    assert [j["_source_job_id"] for j in raw] == ["Playtech:1", "Playtech:2"]
    assert raw[0]["_detail"] == {}
    assert raw[1]["_detail"] == DETAIL
    scraper._fetch_detail.assert_called_once_with("Playtech", "2")


@patch("src.job_scrapers.smartrecruiters_scraper.time.sleep")
def test_fetch_jobs_merges_db_companies_and_survives_a_failing_company(_sleep):
    scraper = _scraper()
    scraper._load_existing_ids = MagicMock(return_value=set())
    scraper._load_db_config = MagicMock(
        return_value=[
            {"company_id": "Sixt", "display_name": "SIXT"},
            {"company_id": "NoName"},
            {"unrelated": "row"},
        ]
    )

    def fake_listings(company_id):
        if company_id == "Playtech":
            raise RuntimeError("down")
        return [{"id": "9", "_company_id": company_id}]

    scraper._fetch_company_listings = fake_listings
    scraper._fetch_detail = MagicMock(return_value={})

    raw = scraper._fetch_jobs()

    assert scraper.companies == {
        "Playtech": "Playtech Ltd",
        "Sixt": "SIXT",
        "NoName": "NoName",
    }
    assert [j["_source_job_id"] for j in raw] == ["Sixt:9", "NoName:9"]
    # Display name from the DB row is what _parse_job reports.
    assert scraper._parse_job(raw[0])["company"] == "SIXT"
