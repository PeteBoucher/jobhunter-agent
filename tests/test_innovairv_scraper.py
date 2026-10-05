"""Tests for the Innova-IRV scraper."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

from src.job_scrapers.base_scraper import validate_job_batch, validate_parsed_job
from src.job_scrapers.innovairv_scraper import CAREERS_URL, InnovaIRVScraper


def _block(slug="rf-design-engineer", title="RF Design Engineer", link=True):
    link_html = (
        f'<div class="btn-block"><a class="btn" '
        f'href="https://innovairv.com/en/empleos/{slug}/">Apply</a></div>'
        if link
        else ""
    )
    return f"""
    <div class="grid__block">
      <h3 class="block__title"> {title} </h3>
      <div class="block__texto"><p>Design   RF front-ends</p>
        <p>for 5G.</p></div>
      {link_html}
    </div>"""


def _page(blocks_html):
    resp = MagicMock()
    resp.text = f'<html><body><div class="grid__empleos">{blocks_html}</div></body>'
    return resp


def _scraper():
    return InnovaIRVScraper(MagicMock())


@patch("src.job_scrapers.innovairv_scraper.requests.get")
def _parse_all(blocks_html, mock_get):
    mock_get.return_value = _page(blocks_html)
    scraper = _scraper()
    return [scraper._parse_job(raw) for raw in scraper._fetch_jobs()]


@patch("src.job_scrapers.innovairv_scraper.requests.get")
def test_fetch_jobs_returns_one_entry_per_block(mock_get):
    mock_get.return_value = _page(_block("a") + _block("b"))

    raw = _scraper()._fetch_jobs()

    assert mock_get.call_args.args[0] == CAREERS_URL
    assert len(raw) == 2
    assert all("block__title" in r["_block"] for r in raw)


@patch("src.job_scrapers.innovairv_scraper.requests.get")
def test_fetch_jobs_returns_empty_on_error_or_no_blocks(mock_get):
    mock_get.side_effect = requests.ConnectionError("down")
    assert _scraper()._fetch_jobs() == []

    mock_get.side_effect = None
    mock_get.return_value = _page("")
    assert _scraper()._fetch_jobs() == []


def test_parse_job_matches_schema():
    (parsed,) = _parse_all(_block())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "rf-design-engineer"
    assert parsed["title"] == "RF Design Engineer"
    assert parsed["company"] == "Innova-IRV"
    assert parsed["location"] == "Málaga, Spain"
    assert parsed["description"] == "Design RF front-ends for 5G."
    assert parsed["apply_url"] == "https://innovairv.com/en/empleos/rf-design-engineer/"
    assert (datetime.now(timezone.utc) - parsed["posted_date"]).total_seconds() < 5


def test_parse_job_country_is_lowercase_iso2():
    # Regression: was "ES", which JobSearcher's case-sensitive country
    # filter (lowercase codes) never matched.
    (parsed,) = _parse_all(_block())
    assert parsed["country"] == "es"


def test_parse_job_without_link_falls_back_to_listing_page_and_title_slug():
    (parsed,) = _parse_all(_block(title="Analog IC Designer (Senior)", link=False))

    assert parsed["apply_url"] == CAREERS_URL
    assert parsed["source_job_id"] == "analog-ic-designer-senior"


def test_parse_job_without_title_is_skipped():
    parsed = _scraper()._parse_job({"_block": '<div class="grid__block"></div>'})
    assert parsed == {}


def test_distinct_jobs_pass_the_batch_check():
    parsed = _parse_all(
        _block("rf-engineer", "RF Engineer") + _block("layout", "Layout Engineer")
    )
    assert validate_job_batch(parsed) == []
