"""Tests for the DeJobs / JobSyn scraper."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
import requests

from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.dejobs_scraper import (
    SEARCH_URL,
    DeJobsCompany,
    DeJobsScraper,
    _infer_remote,
    _parse_date,
)

COMPANY = DeJobsCompany(hostname="nttdata.dejobs.org", name="NTT Data", max_jobs=5)


def _scraper(companies=None):
    scraper = DeJobsScraper(MagicMock(), companies=companies or [COMPANY])
    scraper._http = MagicMock()
    scraper._load_db_config = MagicMock(return_value=[])
    return scraper


def _page(n, total_pages, start=0):
    resp = MagicMock()
    resp.json.return_value = {
        "jobs": [{"guid": f"G{start + i}"} for i in range(n)],
        "pagination": {"total_pages": total_pages},
    }
    return resp


def _raw(**overrides):
    raw = {
        "guid": "ABC123",
        "title_exact": "Data Engineer",
        "company_exact": "NTT DATA Services",
        "location_exact": "Madrid, ESP",
        "city_exact": "Madrid",
        "description": "Build pipelines. This is a hybrid role.",
        "date_new": "2026-08-20T10:00:00Z",
        "date_added": "2026-08-01T10:00:00Z",
        "_company": COMPANY,
    }
    raw.update(overrides)
    return raw


@pytest.mark.parametrize(
    "description,title,expected",
    [
        ("Work from our office", "Engineer", None),
        ("Fully remote", "Engineer", "remote"),
        ("Office based", "Remote Engineer", "remote"),
        ("Remote with hybrid option", "Engineer", "hybrid"),
        ("", "", None),
    ],
)
def test_infer_remote(description, title, expected):
    assert _infer_remote(description, title) == expected


def test_parse_date_handles_z_suffix_and_offsets():
    assert _parse_date("2026-08-20T10:00:00Z") == datetime(2026, 8, 20, 10, 0)
    assert _parse_date("2026-08-20T12:00:00+02:00") == datetime(2026, 8, 20, 10, 0)


def test_parse_date_falls_back_to_now():
    assert (datetime.utcnow() - _parse_date("")).total_seconds() < 5
    assert (datetime.utcnow() - _parse_date("nope")).total_seconds() < 5


def test_parse_job_matches_schema():
    parsed = _scraper()._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "nttdata.dejobs.org:ABC123"
    assert parsed["title"] == "Data Engineer"
    assert parsed["company"] == "NTT DATA Services"
    assert parsed["location"] == "Madrid, ESP"
    assert parsed["remote"] == "hybrid"
    assert parsed["apply_url"] == "https://de.jobsyn.org/ABC12310"
    assert parsed["posted_date"] == datetime(2026, 8, 20, 10, 0)


def test_parse_job_fallbacks():
    parsed = _scraper()._parse_job(
        _raw(company_exact=None, location_exact=None, date_new=None, description=None)
    )

    assert validate_parsed_job(parsed) == []
    assert parsed["company"] == "NTT Data"
    assert parsed["location"] == "Madrid"
    assert parsed["posted_date"] == datetime(2026, 8, 1, 10, 0)
    assert parsed["description"] is None
    assert parsed["remote"] is None


def test_parse_job_without_guid_fails_validation():
    # No GUID means no apply link can be built — the validator must flag
    # it rather than a link to "https://de.jobsyn.org/10" being stored.
    parsed = _scraper()._parse_job(_raw(guid=None))
    assert parsed["apply_url"] is None
    assert any("apply_url" in p for p in validate_parsed_job(parsed))


def test_parse_job_truncates_description():
    parsed = _scraper()._parse_job(_raw(description="x" * 6000))
    assert len(parsed["description"]) == 5000


def test_fetch_company_paginates_with_origin_header():
    scraper = _scraper()
    scraper._http.get.side_effect = [_page(2, 2), _page(2, 2, start=2)]

    listings = scraper._fetch_company(COMPANY)

    assert [j["guid"] for j in listings] == ["G0", "G1", "G2", "G3"]
    assert all(j["_company"] is COMPANY for j in listings)
    calls = scraper._http.get.call_args_list
    assert all(c.args[0] == SEARCH_URL for c in calls)
    assert [c.kwargs["params"]["page"] for c in calls] == ["1", "2"]
    assert all(c.kwargs["headers"] == {"x-origin": COMPANY.hostname} for c in calls)


def test_fetch_company_truncates_to_max_jobs():
    scraper = _scraper()
    scraper._http.get.side_effect = lambda *a, **kw: _page(3, total_pages=50)

    listings = scraper._fetch_company(COMPANY)

    assert len(listings) == COMPANY.max_jobs
    assert scraper._http.get.call_count == 2


def test_fetch_company_stops_on_empty_page_and_on_error():
    scraper = _scraper()
    scraper._http.get.side_effect = [_page(2, 9), _page(0, 9)]
    assert len(scraper._fetch_company(COMPANY)) == 2

    scraper._http.get.side_effect = [_page(2, 9), requests.ConnectionError("down")]
    assert len(scraper._fetch_company(COMPANY)) == 2


def test_fetch_company_missing_pagination_means_single_page():
    scraper = _scraper()
    resp = MagicMock()
    resp.json.return_value = {"jobs": [{"guid": "G0"}]}
    scraper._http.get.return_value = resp

    assert len(scraper._fetch_company(COMPANY)) == 1
    assert scraper._http.get.call_count == 1


def test_fetch_jobs_merges_db_companies():
    scraper = _scraper()
    scraper._load_db_config = MagicMock(
        return_value=[
            {"hostname": "acme.dejobs.org", "name": "Acme", "max_jobs": "12"},
            {"hostname": "noname.dejobs.org"},
            {"name": "No hostname"},
        ]
    )
    seen = []

    def fake_fetch(company):
        seen.append(company)
        return [{"guid": company.hostname}]

    scraper._fetch_company = fake_fetch

    raw = scraper._fetch_jobs()

    assert [(c.hostname, c.name, c.max_jobs) for c in seen] == [
        ("nttdata.dejobs.org", "NTT Data", 5),
        ("acme.dejobs.org", "Acme", 12),
        ("noname.dejobs.org", "noname.dejobs.org", 500),
    ]
    assert len(raw) == 3
