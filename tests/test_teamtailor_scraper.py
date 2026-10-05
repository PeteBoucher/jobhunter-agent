"""Tests for the Teamtailor scraper."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import requests

from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.teamtailor_scraper import (
    TeamtailorBoard,
    TeamtailorScraper,
    _parse_date,
    _parse_location,
    _parse_remote,
    _slug,
    _strip_html,
)

BOARD = TeamtailorBoard(
    company="The Workshop", career_url="https://careers.theworkshop.com"
)


def _scraper(boards=None):
    scraper = TeamtailorScraper(MagicMock(), boards=boards or [BOARD])
    scraper._http = MagicMock()
    scraper._load_db_config = MagicMock(return_value=[])
    return scraper


def _raw(**overrides):
    raw = {
        "id": "feed-id",
        "title": "Backend Engineer",
        "url": "https://careers.theworkshop.com/jobs/6571-backend-engineer",
        "date_published": "2026-08-20T12:00:00+02:00",
        "content_html": "<p>Feed body</p>",
        "_board": BOARD,
        "_jobposting": {
            "title": "Backend Engineer",
            "identifier": {"value": 6571},
            "description": "<p>Join our <b>platform</b> team in Málaga.</p>",
            "datePosted": "2026-08-01T00:00:00+00:00",
            "jobLocation": [
                {"address": {"addressLocality": "Málaga", "addressCountry": "ES"}}
            ],
        },
    }
    raw.update(overrides)
    return raw


def test_slug():
    assert _slug("The Workshop") == "the-workshop"
    assert _slug("  Oatly AB! ") == "oatly-ab"


def test_strip_html():
    assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"


@pytest.mark.parametrize(
    "job_location,expected",
    [
        (None, (None, None)),
        ([], (None, None)),
        (
            [{"address": {"addressLocality": "Madrid", "addressCountry": "ES"}}],
            ("Madrid", "es"),
        ),
        ({"address": {"addressLocality": "Stockholm"}}, ("Stockholm", None)),
        ([{"name": "HQ"}], (None, None)),
    ],
)
def test_parse_location(job_location, expected):
    assert _parse_location(job_location) == expected


@pytest.mark.parametrize(
    "jp,expected",
    [
        ({"jobLocationType": "TELECOMMUTE"}, "remote"),
        ({"jobLocationType": "telecommute", "title": "Hybrid PM"}, "remote"),
        ({"title": "Hybrid Product Manager"}, "hybrid"),
        ({"description": "This is a fully remote role."}, "remote"),
        ({"title": "Engineer", "description": "Office based."}, None),
        # Only the first 500 chars of the description are scanned.
        ({"description": "x" * 500 + " remote"}, None),
        ({}, None),
    ],
)
def test_parse_remote(jp, expected):
    assert _parse_remote(jp) == expected


def test_parse_date_converts_to_naive_utc():
    assert _parse_date("2026-08-20T12:00:00+02:00") == datetime(2026, 8, 20, 10, 0)
    assert _parse_date("2026-08-20T12:00:00") == datetime(2026, 8, 20, 12, 0)


def test_parse_date_falls_back_to_now():
    assert (datetime.utcnow() - _parse_date("")).total_seconds() < 5
    assert (datetime.utcnow() - _parse_date("nope")).total_seconds() < 5


def test_parse_job_matches_schema():
    parsed = _scraper()._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "the-workshop:6571"
    assert parsed["title"] == "Backend Engineer"
    assert parsed["company"] == "The Workshop"
    assert parsed["location"] == "Málaga"
    assert parsed["country"] == "es"
    assert parsed["remote"] is None
    assert parsed["description"] == "Join our platform team in Málaga."
    assert parsed["apply_url"] == _raw()["url"]
    # The feed's date_published wins over the JobPosting's datePosted.
    assert parsed["posted_date"] == datetime(2026, 8, 20, 10, 0)


def test_parse_job_falls_back_to_feed_fields_without_jobposting():
    raw = _raw(_jobposting=None, url=None, date_published=None)
    parsed = _scraper()._parse_job(raw)

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "the-workshop:feed-id"
    assert parsed["description"] == "Feed body"
    assert parsed["apply_url"] == BOARD.career_url
    assert parsed["location"] is None
    assert parsed["country"] is None


def test_parse_job_truncates_description():
    raw = _raw(_jobposting={"description": "<p>" + "x" * 6000 + "</p>"})
    assert len(_scraper()._parse_job(raw)["description"]) == 5000


def test_fetch_jobs_tags_items_with_their_board():
    scraper = _scraper()
    scraper._http.get.return_value.json.return_value = {
        "items": [{"id": "1"}, {"id": "2"}]
    }

    raw = scraper._fetch_jobs()

    scraper._http.get.assert_called_once_with(
        "https://careers.theworkshop.com/jobs.json", timeout=15
    )
    assert [item["id"] for item in raw] == ["1", "2"]
    assert all(item["_board"] is BOARD for item in raw)


def test_fetch_jobs_merges_db_boards_and_skips_a_failing_board():
    scraper = _scraper()
    scraper._load_db_config = MagicMock(
        return_value=[
            {"company": "Acme", "career_url": "https://acme.teamtailor.com/"},
            {"career_url": "https://noname.teamtailor.com"},
            {"company": "No URL"},
        ]
    )
    acme, noname = MagicMock(), MagicMock()
    acme.json.return_value = {"items": [{"id": "1"}]}
    noname.json.return_value = {"items": [{"id": "2"}]}
    scraper._http.get.side_effect = [requests.ConnectionError("down"), acme, noname]

    raw = scraper._fetch_jobs()

    urls = [c.args[0] for c in scraper._http.get.call_args_list]
    assert urls == [
        "https://careers.theworkshop.com/jobs.json",
        "https://acme.teamtailor.com/jobs.json",  # trailing slash not doubled
        "https://noname.teamtailor.com/jobs.json",
    ]
    assert [item["_board"].company for item in raw] == [
        "Acme",
        "https://noname.teamtailor.com",
    ]
