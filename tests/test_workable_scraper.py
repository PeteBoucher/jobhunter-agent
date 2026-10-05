"""Tests for the Workable scraper.

Regression coverage for a real bug: `_strip_html()` flattened the
requirements HTML's `<li>` items into one unpunctuated string, which
`job_matcher` then counted as a single requirement — any one skill-word
overlap scored 35/35 on skills (found via a 360dialog job notifying at 85%).
"""

from datetime import datetime
from unittest.mock import MagicMock

import requests

from src.job_matcher import _requirement_items
from src.job_scrapers.base_scraper import validate_parsed_job
from src.job_scrapers.workable_scraper import (
    WorkableCompany,
    WorkableScraper,
    _parse_date,
    _strip_html,
)

REQUIREMENTS_HTML = (
    "<p><strong>Requirements</strong></p><ul>"
    "<li>3+ years of experience in project management</li>"
    "<li>Strong stakeholder management</li>"
    "<li>Solid understanding of <em>Agile/Scrum</em> methodologies</li>"
    "</ul>"
)


def _scraper(detail=None, detail_error=None):
    scraper = WorkableScraper(MagicMock())
    scraper._http = MagicMock()
    if detail_error:
        scraper._http.get.side_effect = detail_error
    else:
        scraper._http.get.return_value.json.return_value = detail or {}
    return scraper


def _raw(**overrides):
    raw = {
        "shortcode": "ABC123",
        "title": "Project Manager EMEA | Remote",
        "remote": True,
        "location": {"city": "Belgrade", "countryCode": "RS"},
        "department": ["Operations"],
        "published": "2026-08-20T10:00:00.000Z",
        "_company": WorkableCompany(slug="360dialog-gmbh", name="360dialog"),
    }
    raw.update(overrides)
    return raw


def test_strip_html_keeps_list_items_on_separate_lines():
    assert _strip_html(REQUIREMENTS_HTML).split("\n") == [
        "Requirements",
        "3+ years of experience in project management",
        "Strong stakeholder management",
        "Solid understanding of Agile/Scrum methodologies",
    ]


def test_strip_html_inline_tags_do_not_break_lines():
    assert _strip_html("<p>Know <b>Python</b> and <i>SQL</i></p>") == (
        "Know Python and SQL"
    )


def test_strip_html_collapses_whitespace_and_blank_lines():
    assert _strip_html("<ul>\n  <li> One </li>\n\n  <li>Two</li>\n</ul>") == "One\nTwo"


def test_requirements_split_into_one_item_per_list_entry():
    scraper = _scraper(
        {"description": "<p>About us</p>", "requirements": REQUIREMENTS_HTML}
    )
    parsed = scraper._parse_job(_raw())
    assert len(_requirement_items(parsed["requirements"])) == 4


def test_parse_job_matches_base_scraper_schema():
    scraper = _scraper(
        {"description": "<p>About us</p>", "requirements": REQUIREMENTS_HTML}
    )
    parsed = scraper._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["source_job_id"] == "360dialog-gmbh:ABC123"
    assert parsed["company"] == "360dialog"
    assert parsed["apply_url"] == "https://apply.workable.com/360dialog-gmbh/j/ABC123/"
    assert parsed["remote"] == "remote"
    assert parsed["location"] == "Belgrade"
    assert parsed["country"] == "rs"
    assert parsed["department"] == "Operations"
    assert parsed["description"] == "About us"
    assert isinstance(parsed["posted_date"], datetime)
    assert parsed["posted_date"].tzinfo is None


def test_parse_job_non_remote_and_missing_optional_fields():
    scraper = _scraper({})
    parsed = scraper._parse_job(_raw(remote=False, location=None, department=None))

    assert validate_parsed_job(parsed) == []
    assert parsed["remote"] is None
    assert parsed["location"] is None
    assert parsed["country"] is None
    assert parsed["department"] is None
    assert parsed["description"] is None
    assert parsed["requirements"] is None


def test_parse_job_survives_detail_fetch_failure():
    scraper = _scraper(detail_error=requests.ConnectionError("boom"))
    parsed = scraper._parse_job(_raw())

    assert validate_parsed_job(parsed) == []
    assert parsed["description"] is None
    assert parsed["requirements"] is None


def test_requirements_truncated_to_2000_chars():
    html = (
        "<ul>"
        + "".join(f"<li>Requirement number {i}</li>" for i in range(200))
        + "</ul>"
    )
    scraper = _scraper({"requirements": html})
    assert len(scraper._parse_job(_raw())["requirements"]) == 2000


def test_fetch_company_follows_next_page_token():
    scraper = _scraper()
    company = WorkableCompany(slug="acme", name="Acme")
    page1, page2 = MagicMock(), MagicMock()
    page1.json.return_value = {"results": [{"shortcode": "A"}], "nextPage": "tok"}
    page2.json.return_value = {"results": [{"shortcode": "B"}]}
    scraper._http.post.side_effect = [page1, page2]

    listings = scraper._fetch_company(company)

    assert [j["shortcode"] for j in listings] == ["A", "B"]
    assert all(j["_company"] is company for j in listings)
    assert scraper._http.post.call_args_list[1].kwargs["json"]["token"] == "tok"


def test_fetch_company_returns_empty_on_http_error():
    scraper = _scraper()
    scraper._http.post.side_effect = requests.ConnectionError("down")
    assert scraper._fetch_company(WorkableCompany(slug="acme", name="Acme")) == []


def test_parse_date_handles_invalid_and_empty():
    assert isinstance(_parse_date(""), datetime)
    assert isinstance(_parse_date("not-a-date"), datetime)
