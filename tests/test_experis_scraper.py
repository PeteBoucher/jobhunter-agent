"""Tests for the Experis Spain scraper."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.experis_scraper import LIST_URL, ExperisScraper

DETAIL_HTML = """
<html><body>
  <nav class="site-content-nav">Buscar trabajo</nav>
  <div class="details-rich-text">
    <p>Buscamos un <b>desarrollador</b> Java.</p>
    <p>Modalidad 100% remoto.</p>
  </div>
</body></html>
"""


def _scraper():
    scraper = ExperisScraper(MagicMock())
    scraper._http = MagicMock()
    return scraper


def _page(n, total, start=0):
    resp = MagicMock()
    resp.json.return_value = {
        "jobsItems": [{"jobID": f"J{start + i}"} for i in range(n)],
        "filters": {"totalCount": total},
    }
    return resp


def _raw(**overrides):
    raw = {
        "jobID": "12345",
        "jobURL": "/es/oferta-de-empleo/12345/desarrollador-java",
        "jobTitle": "Desarrollador Java",
        "companyName": "",
        "jobLocation": "Madrid",
        "publishfromDate": "2026-08-26T08:40:54Z",
    }
    raw.update(overrides)
    return raw


def test_fetch_jobs_treats_offset_as_page_number():
    # Regression: "offset" is a page index on this API. Incrementing it by
    # `limit` skipped every page after the first.
    scraper = _scraper()
    scraper._http.post.side_effect = [
        _page(50, total=120),
        _page(50, total=120, start=50),
        _page(20, total=120, start=100),
    ]

    jobs = scraper._fetch_jobs()

    assert len(jobs) == 120
    calls = scraper._http.post.call_args_list
    assert all(c.args[0] == LIST_URL for c in calls)
    assert [c.kwargs["json"]["filter"]["offset"] for c in calls] == [0, 1, 2]
    assert [c.kwargs["json"]["filter"]["totalCount"] for c in calls] == [0, 120, 120]


def test_fetch_jobs_stops_on_empty_page_even_if_total_not_reached():
    scraper = _scraper()
    scraper._http.post.side_effect = [_page(50, total=500), _page(0, total=500)]
    assert len(scraper._fetch_jobs()) == 50


def test_fetch_jobs_without_total_count_fetches_one_page():
    scraper = _scraper()
    resp = MagicMock()
    resp.json.return_value = {"jobsItems": [{"jobID": "J0"}]}
    scraper._http.post.return_value = resp

    assert len(scraper._fetch_jobs()) == 1
    assert scraper._http.post.call_count == 1


def test_fetch_jobs_keeps_earlier_pages_on_error():
    scraper = _scraper()
    scraper._http.post.side_effect = [
        _page(50, total=500),
        requests.ConnectionError("down"),
    ]
    assert len(scraper._fetch_jobs()) == 50


def test_parse_job_matches_schema():
    scraper = _scraper()
    scraper._http.get.return_value.text = DETAIL_HTML

    parsed = scraper._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "12345"
    assert parsed["title"] == "Desarrollador Java"
    assert parsed["company"] == "Experis"
    assert parsed["location"] == "Madrid"
    assert parsed["country"] == "es"
    assert parsed["remote"] == "remote"
    assert parsed["apply_url"] == (
        "https://www.experis.es/es/oferta-de-empleo/12345/desarrollador-java"
    )
    assert parsed["posted_date"] == datetime(
        2026, 8, 26, 8, 40, 54, tzinfo=timezone.utc
    )
    scraper._http.get.assert_called_once_with(parsed["apply_url"], timeout=15)


def test_description_comes_only_from_the_rich_text_container():
    scraper = _scraper()
    scraper._http.get.return_value.text = DETAIL_HTML

    description = scraper._parse_job(_raw())["description"]

    assert description == "Buscamos un desarrollador Java. Modalidad 100% remoto."
    assert "Buscar trabajo" not in description


def test_parse_job_uses_listed_company_name():
    scraper = _scraper()
    scraper._http.get.return_value.text = DETAIL_HTML
    assert scraper._parse_job(_raw(companyName="Acme SL"))["company"] == "Acme SL"


def test_parse_job_without_url_skips_detail_fetch_and_fails_validation():
    scraper = _scraper()
    parsed = scraper._parse_job(_raw(jobURL=""))

    scraper._http.get.assert_not_called()
    assert parsed["description"] == ""
    assert parsed["remote"] is None
    assert any("apply_url" in p for p in validate_parsed_job(parsed))


def test_parse_job_bad_or_missing_date_falls_back_to_now():
    scraper = _scraper()
    scraper._http.get.return_value.text = DETAIL_HTML
    for value in ("not-a-date", ""):
        posted = scraper._parse_job(_raw(publishfromDate=value))["posted_date"]
        assert (datetime.now(timezone.utc) - posted).total_seconds() < 5


def test_fetch_job_description_handles_errors_and_missing_container():
    scraper = _scraper()
    scraper._http.get.side_effect = requests.ConnectionError("down")
    assert scraper._fetch_job_description("https://x") == ""

    scraper._http.get.side_effect = None
    scraper._http.get.return_value.text = "<html><body><p>No job</p></body></html>"
    assert scraper._fetch_job_description("https://x") == ""


def test_fetch_job_description_truncates():
    scraper = _scraper()
    scraper._http.get.return_value.text = (
        '<div class="details-rich-text">' + "x" * 6000 + "</div>"
    )
    assert len(scraper._fetch_job_description("https://x")) == 5000


@pytest.mark.parametrize(
    "description,expected",
    [
        ("", None),
        ("Puesto en Madrid", None),
        ("Modalidad 100% remoto", "remote"),
        ("Fully remote position", "remote"),
        ("Posibilidad de teletrabajo", "remote"),
        ("Trabajo presencial en Barcelona", "onsite"),
        ("On-site role", "onsite"),
        ("Trabajarás en nuestras oficinas", "onsite"),
        # Remote indicators are checked first.
        ("Presencial con opción de teletrabajo", "remote"),
        # Word boundary: "remotos" is not "remoto".
        ("Gestión de equipos remotos", None),
    ],
)
def test_infer_remote(description, expected):
    assert _scraper()._infer_remote(description) == expected
