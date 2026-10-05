"""Tests for the Indra Group (SAP SuccessFactors) scraper."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.indragroup_scraper import (
    PAGE_SIZE,
    IndraGroupScraper,
    _parse_date,
)


def _row(job_id, title="Ingeniero/a de Software", location="Madrid, ES"):
    return f"""
    <tr class="data-row">
      <td class="colTitle">
        <a class="jobTitle-link" href="/job/Madrid-Ingeniero-28001/{job_id}/">
          {title}
        </a>
        <span class="jobDate"> 17 ago 2026 </span>
      </td>
      <td class="colLocation"><span class="jobLocation"> {location} </span></td>
    </tr>"""


def _page(rows_html):
    resp = MagicMock()
    resp.text = f"<html><body><table>{rows_html}</table></body></html>"
    return resp


def _scraper():
    return IndraGroupScraper(MagicMock())


@pytest.mark.parametrize(
    "text,expected",
    [
        ("17 ago 2026", datetime(2026, 8, 17, tzinfo=timezone.utc)),
        ("  1 ENE 2026 ", datetime(2026, 1, 1, tzinfo=timezone.utc)),
        ("3 dic 2025", datetime(2025, 12, 3, tzinfo=timezone.utc)),
        ("17 aug 2026", None),  # English month abbreviation
        ("31 feb 2026", None),  # impossible date
        ("ayer", None),
        ("", None),
    ],
)
def test_parse_date(text, expected):
    assert _parse_date(text) == expected


@patch("src.job_scrapers.indragroup_scraper.requests.get")
def test_fetch_jobs_extracts_rows(mock_get):
    mock_get.return_value = _page(_row(1001) + _row(1002, title="Analista"))

    jobs = _scraper()._fetch_jobs()

    assert jobs == [
        {
            "source_job_id": "1001",
            "title": "Ingeniero/a de Software",
            "apply_url": (
                "https://careers.indragroup.com/job/Madrid-Ingeniero-28001/1001/"
            ),
            "location": "Madrid, ES",
            "posted_date": datetime(2026, 8, 17, tzinfo=timezone.utc),
        },
        {
            "source_job_id": "1002",
            "title": "Analista",
            "apply_url": (
                "https://careers.indragroup.com/job/Madrid-Ingeniero-28001/1002/"
            ),
            "location": "Madrid, ES",
            "posted_date": datetime(2026, 8, 17, tzinfo=timezone.utc),
        },
    ]
    # A short page is the last page.
    assert mock_get.call_count == 1


@patch("src.job_scrapers.indragroup_scraper.requests.get")
def test_fetch_jobs_paginates_by_startrow(mock_get):
    full = "".join(_row(i) for i in range(PAGE_SIZE))
    mock_get.side_effect = [_page(full), _page(_row(9999))]

    jobs = _scraper()._fetch_jobs()

    assert len(jobs) == PAGE_SIZE + 1
    urls = [c.args[0] for c in mock_get.call_args_list]
    assert urls[0].endswith("&startrow=0")
    assert urls[1].endswith(f"&startrow={PAGE_SIZE}")


@patch("src.job_scrapers.indragroup_scraper.requests.get")
def test_fetch_jobs_skips_rows_without_a_link_or_numeric_id(mock_get):
    rows = (
        '<tr class="data-row"><td>No link here</td></tr>'
        '<tr class="data-row"><td><a class="jobTitle-link" href="/job/no-id/">'
        "X</a></td></tr>" + _row(7)
    )
    mock_get.return_value = _page(rows)

    jobs = _scraper()._fetch_jobs()

    assert [j["source_job_id"] for j in jobs] == ["7"]


@patch("src.job_scrapers.indragroup_scraper.requests.get")
def test_fetch_jobs_row_without_date_or_location(mock_get):
    mock_get.return_value = _page(
        '<tr class="data-row"><td>'
        '<a class="jobTitle-link" href="/job/slug/55/">Dev</a></td></tr>'
    )

    (job,) = _scraper()._fetch_jobs()

    assert job["location"] is None
    assert job["posted_date"] is None


@patch("src.job_scrapers.indragroup_scraper.requests.get")
def test_fetch_jobs_empty_page_and_http_error(mock_get):
    mock_get.return_value = _page("")
    assert _scraper()._fetch_jobs() == []

    mock_get.side_effect = requests.ConnectionError("down")
    assert _scraper()._fetch_jobs() == []


def test_parse_job_matches_schema():
    raw = {
        "source_job_id": "1001",
        "title": "Ingeniero/a de Software",
        "apply_url": "https://careers.indragroup.com/job/x/1001/",
        "location": "Madrid, ES",
        "posted_date": datetime(2026, 8, 17, tzinfo=timezone.utc),
    }
    parsed = _scraper()._parse_job(raw)

    assert validate_parsed_job(parsed) == []
    assert parsed["company"] == "Indra Group"
    assert parsed["location"] == "Madrid, ES"
    assert parsed["apply_url"] == raw["apply_url"]
    assert parsed["posted_date"] == raw["posted_date"]


@pytest.mark.parametrize(
    "location,expected",
    [
        # Regression: this was stored as "ES". JobSearcher's country filter is
        # a case-sensitive match against lowercase codes, so every Indra job
        # dropped out of country-filtered searches.
        ("Madrid, ES", "es"),
        ("Alcobendas, Madrid, ES", "es"),
        ("Lisboa, pt", "pt"),
        ("Madrid", None),
        ("Madrid, Spain", None),
        (None, None),
    ],
)
def test_parse_job_country_is_lowercase_iso2(location, expected):
    raw = {"source_job_id": "1", "title": "T", "apply_url": "u", "location": location}
    assert _scraper()._parse_job(raw)["country"] == expected
