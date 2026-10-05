"""Tests for the Workday scraper."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.workday_scraper import (
    PAGE_SIZE,
    WorkdayPortal,
    WorkdayScraper,
    _parse_posted_on,
    _parse_remote,
    _strip_html,
)

PORTAL = WorkdayPortal(
    slug="maersk",
    portal="Maersk_Careers",
    company="Maersk",
    industry="Logistics / Shipping",
    size="Enterprise (100k+)",
    max_jobs=40,
)


def _scraper(portals=None):
    scraper = WorkdayScraper(MagicMock(), portals=portals or [PORTAL])
    scraper._http = MagicMock()
    return scraper


def _page(postings, total):
    resp = MagicMock()
    resp.json.return_value = {"jobPostings": postings, "total": total}
    return resp


def _postings(n, start=0):
    return [
        {"jobReqId": f"R{start + i}", "externalPath": f"/job/Copenhagen/R{start + i}"}
        for i in range(n)
    ]


def test_portal_urls():
    assert PORTAL.base_url == "https://maersk.wd3.myworkdayjobs.com"
    assert PORTAL.search_url == (
        "https://maersk.wd3.myworkdayjobs.com/wday/cxs/maersk/Maersk_Careers/jobs"
    )
    assert PORTAL.apply_base == (
        "https://maersk.wd3.myworkdayjobs.com/en-US/Maersk_Careers"
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Copenhagen, Denmark", None),
        ("Remote - UK", "remote"),
        ("Hybrid, London", "hybrid"),
        ("Remote / Hybrid", "hybrid"),
        ("", None),
    ],
)
def test_parse_remote(text, expected):
    assert _parse_remote(text) == expected


@pytest.mark.parametrize(
    "text,days",
    [
        ("Posted Today", 0),
        ("Posted 3 Days Ago", 3),
        ("Posted 30+ Days Ago", 30),
        ("Posted Yesterday", 0),  # unrecognised wording falls back to now
        ("", 0),
    ],
)
def test_parse_posted_on(text, days):
    expected = datetime.utcnow() - timedelta(days=days)
    assert abs((_parse_posted_on(text) - expected).total_seconds()) < 5


def test_strip_html():
    assert _strip_html("<p>Hello <b>world</b></p>\n<p>again</p>") == "Hello world again"


def test_parse_job_matches_schema():
    raw = {
        "title": "Software Engineer",
        "externalPath": "/job/Copenhagen/Engineer_R123",
        "locationsText": "Copenhagen, Denmark",
        "bulletFields": ["Technology", "R123"],
        "postedOn": "Posted 2 Days Ago",
        "_portal": PORTAL,
        "_source_job_id": "maersk:R123",
        "_description_html": "<p>Build <b>things</b></p>",
    }
    parsed = _scraper()._parse_job(raw)

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "maersk:R123"
    assert parsed["company"] == "Maersk"
    assert parsed["department"] == "Technology"
    assert parsed["location"] == "Copenhagen, Denmark"
    assert parsed["remote"] is None
    assert parsed["description"] == "Build things"
    assert parsed["apply_url"] == (
        "https://maersk.wd3.myworkdayjobs.com/en-US/Maersk_Careers"
        "/job/Copenhagen/Engineer_R123"
    )
    assert parsed["company_industry"] == "Logistics / Shipping"
    assert isinstance(parsed["posted_date"], datetime)


def test_parse_job_without_description_or_path():
    raw = {
        "title": "Analyst",
        "_portal": PORTAL,
        "_source_job_id": "maersk:R9",
        "_description_html": None,
    }
    parsed = _scraper()._parse_job(raw)

    assert validate_parsed_job(parsed) == []
    assert parsed["description"] is None
    assert parsed["location"] is None
    assert parsed["department"] is None
    assert parsed["apply_url"] == PORTAL.apply_base


def test_parse_job_truncates_description():
    raw = {
        "title": "Analyst",
        "_portal": PORTAL,
        "_source_job_id": "maersk:R9",
        "_description_html": "<p>" + "x" * 6000 + "</p>",
    }
    assert len(_scraper()._parse_job(raw)["description"]) == 5000


def test_fetch_portal_listings_paginates_by_offset():
    scraper = _scraper()
    scraper._http.post.side_effect = [
        _page(_postings(PAGE_SIZE), total=25),
        _page(_postings(5, start=PAGE_SIZE), total=25),
    ]

    listings = scraper._fetch_portal_listings(PORTAL)

    assert len(listings) == 25
    assert all(job["_portal"] is PORTAL for job in listings)
    offsets = [c.kwargs["json"]["offset"] for c in scraper._http.post.call_args_list]
    assert offsets == [0, PAGE_SIZE]


def test_fetch_portal_listings_stops_at_max_jobs():
    scraper = _scraper()
    scraper._http.post.side_effect = lambda *a, **kw: _page(
        _postings(PAGE_SIZE), total=1000
    )

    listings = scraper._fetch_portal_listings(PORTAL)

    assert len(listings) == PORTAL.max_jobs
    assert scraper._http.post.call_count == PORTAL.max_jobs // PAGE_SIZE


def test_fetch_portal_listings_keeps_earlier_pages_on_error():
    scraper = _scraper()
    scraper._http.post.side_effect = [
        _page(_postings(PAGE_SIZE), total=100),
        requests.ConnectionError("boom"),
    ]
    assert len(scraper._fetch_portal_listings(PORTAL)) == PAGE_SIZE


def test_fetch_portal_listings_empty_page():
    scraper = _scraper()
    scraper._http.post.return_value = _page([], total=0)
    assert scraper._fetch_portal_listings(PORTAL) == []


def test_fetch_description_builds_detail_url():
    scraper = _scraper()
    scraper._http.get.return_value.json.return_value = {
        "jobPostingInfo": {"jobDescription": "<p>Hi</p>"}
    }

    assert scraper._fetch_description(PORTAL, "/job/Copenhagen/R1") == "<p>Hi</p>"
    scraper._http.get.assert_called_once_with(
        "https://maersk.wd3.myworkdayjobs.com/wday/cxs/maersk/Maersk_Careers"
        "/job/Copenhagen/R1",
        timeout=15,
    )


def test_fetch_description_returns_none_on_error():
    scraper = _scraper()
    scraper._http.get.side_effect = requests.ConnectionError("boom")
    assert scraper._fetch_description(PORTAL, "/job/x") is None


@patch("src.job_scrapers.workday_scraper.time.sleep")
def test_fetch_jobs_only_hydrates_new_jobs(_sleep):
    scraper = _scraper()
    scraper._load_existing_ids = MagicMock(return_value={"maersk:R0"})
    scraper._load_db_config = MagicMock(return_value=[])
    scraper._fetch_portal_listings = MagicMock(return_value=_postings(2))
    scraper._fetch_description = MagicMock(return_value="<p>desc</p>")

    raw = scraper._fetch_jobs()

    assert [j["_source_job_id"] for j in raw] == ["maersk:R0", "maersk:R1"]
    assert raw[0]["_description_html"] is None
    assert raw[1]["_description_html"] == "<p>desc</p>"
    scraper._fetch_description.assert_called_once_with(PORTAL, "/job/Copenhagen/R1")


@patch("src.job_scrapers.workday_scraper.time.sleep")
def test_fetch_jobs_merges_db_portals_and_survives_a_failing_portal(_sleep):
    scraper = _scraper()
    scraper._load_existing_ids = MagicMock(return_value=set())
    scraper._load_db_config = MagicMock(
        return_value=[
            {"slug": "acme", "portal": "Careers", "wd": "wd5", "max_jobs": "7"},
            {"slug": "missing-portal-key"},
        ]
    )
    seen = []

    def fake_listings(portal):
        seen.append(portal)
        if portal.slug == "maersk":
            raise RuntimeError("portal down")
        return [{"jobReqId": "A1"}]

    scraper._fetch_portal_listings = fake_listings
    scraper._fetch_description = MagicMock()

    raw = scraper._fetch_jobs()

    assert [p.slug for p in seen] == ["maersk", "acme"]
    db_portal = seen[1]
    assert (db_portal.company, db_portal.wd, db_portal.max_jobs) == ("acme", "wd5", 7)
    assert [j["_source_job_id"] for j in raw] == ["acme:A1"]
    # No externalPath on the listing, so there is nothing to fetch.
    scraper._fetch_description.assert_not_called()
