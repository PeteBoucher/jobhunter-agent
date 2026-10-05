"""Tests for the TKH Security scraper."""

from unittest.mock import MagicMock

import requests

from src.job_scrapers.base_scraper import validate_job_batch, validate_parsed_job
from src.job_scrapers.tkhsecurity_scraper import CAREERS_URL, TKHSecurityScraper


def _item(job_id=412, title="Embedded Software Engineer", href=None, meta=True):
    href = href if href is not None else f"https://tkhsecurity.com/careers/?id={job_id}"
    meta_html = (
        '<div class="job-item__meta-group"><span>Zoetermeer,</span>'
        "<span>Netherlands</span></div>"
        if meta
        else ""
    )
    return f"""
    <a class="job-item" href="{href}">
      <h5 class="job-item__title"> {title} </h5>
      <span class="job-item__term">Engineering</span>
      {meta_html}
    </a>"""


def _page(items_html):
    return f"""
    <html><body>
      <a class="nav-link" href="/about/">About</a>
      <div class="b-career-api"><div class="b-career-api__list">
        {items_html}
      </div></div>
    </body></html>"""


def _scraper():
    scraper = TKHSecurityScraper(MagicMock())
    scraper._http = MagicMock()
    return scraper


def _parse(item_html):
    scraper = _scraper()
    scraper._http.get.return_value.text = _page(item_html)
    (raw,) = scraper._fetch_jobs()
    return scraper._parse_job(raw)


def test_fetch_jobs_returns_only_job_items():
    scraper = _scraper()
    scraper._http.get.return_value.text = _page(_item(1) + _item(2))

    raw = scraper._fetch_jobs()

    scraper._http.get.assert_called_once_with(CAREERS_URL, timeout=15)
    assert len(raw) == 2
    assert all("job-item__title" in r["_item"] for r in raw)


def test_fetch_jobs_returns_empty_on_error_or_no_items():
    scraper = _scraper()
    scraper._http.get.side_effect = requests.ConnectionError("down")
    assert scraper._fetch_jobs() == []

    scraper._http.get.side_effect = None
    scraper._http.get.return_value.text = _page("")
    assert scraper._fetch_jobs() == []


def test_parse_job_matches_schema():
    parsed = _parse(_item(412))

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "412"
    assert parsed["title"] == "Embedded Software Engineer"
    assert parsed["company"] == "TKH Security"
    assert parsed["location"] == "Zoetermeer, Netherlands"
    assert parsed["apply_url"] == "https://tkhsecurity.com/careers/?id=412"
    # Left for the base class to infer from the location.
    assert parsed["country"] is None
    assert parsed["posted_date"] is None


def test_parse_job_id_from_later_query_parameter():
    parsed = _parse(_item(href="https://tkhsecurity.com/careers/?lang=en&id=77"))
    assert parsed["source_job_id"] == "77"


def test_parse_job_without_id_falls_back_to_title_slug():
    parsed = _parse(
        _item(title="Sales Manager (EMEA)", href="https://tkhsecurity.com/job/")
    )
    assert parsed["source_job_id"] == "sales-manager-emea"


def test_parse_job_without_meta_group_has_no_location():
    assert _parse(_item(meta=False))["location"] is None


def test_parse_job_without_title_is_skipped():
    scraper = _scraper()
    parsed = scraper._parse_job({"_item": '<a class="job-item" href="/x?id=1"></a>'})
    assert parsed == {}


def test_distinct_jobs_pass_the_batch_check():
    scraper = _scraper()
    scraper._http.get.return_value.text = _page(
        _item(1, title="Engineer") + _item(2, title="Designer")
    )
    parsed = [scraper._parse_job(r) for r in scraper._fetch_jobs()]
    assert validate_job_batch(parsed) == []
