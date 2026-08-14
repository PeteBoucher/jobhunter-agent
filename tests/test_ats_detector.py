"""Tests for ATS URL detection utility."""

from unittest.mock import MagicMock, patch

import pytest

from src.job_scrapers.ats_detector import detect_ats

# ── URL pattern tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected_source, expected_config_key",
    [
        (
            "https://boards.greenhouse.io/stripe",
            "greenhouse",
            {"token": "stripe"},
        ),
        (
            "https://job-boards.greenhouse.io/cloudflare",
            "greenhouse",
            {"token": "cloudflare"},
        ),
        (
            "https://jobs.lever.co/spotify",
            "lever",
            {"company": "spotify"},
        ),
        (
            "https://app.ashbyhq.com/careers/openai",
            "ashby",
            {"subdomain": "openai"},
        ),
        (
            "https://accenture.wd3.myworkdayjobs.com/Accenture_Careers",
            "workday",
            {"slug": "accenture", "portal": "Accenture_Careers", "wd": "wd3"},
        ),
        (
            "https://apply.workable.com/360dialog-gmbh/",
            "workable",
            {"slug": "360dialog-gmbh"},
        ),
        (
            "https://nttdata.dejobs.org/jobs/",
            "dejobs",
            {"hostname": "nttdata.dejobs.org"},
        ),
        (
            "https://jobs.smartrecruiters.com/Stripe1",
            "smartrecruiters",
            {"company_id": "Stripe1"},
        ),
    ],
)
def test_detect_ats_url_patterns(url, expected_source, expected_config_key):
    """URL pattern matching detects ATS without fetching the page."""
    result = detect_ats(url, fetch_page=False)
    assert result is not None
    source_name, config = result
    assert source_name == expected_source
    for key, value in expected_config_key.items():
        assert config.get(key) == value


def test_detect_ats_unknown_url_no_fetch():
    """Unrecognised URL returns None when page fetching is disabled."""
    result = detect_ats("https://careers.someunknowncompany.com/jobs", fetch_page=False)
    assert result is None


def test_detect_ats_workday_various_wd_numbers():
    """Workday wd variant is extracted correctly for different WD numbers."""
    for wd in ("wd1", "wd5", "wd103"):
        url = f"https://salesforce.{wd}.myworkdayjobs.com/Salesforce"
        result = detect_ats(url, fetch_page=False)
        assert result is not None
        source_name, config = result
        assert source_name == "workday"
        assert config["wd"] == wd
        assert config["slug"] == "salesforce"
        assert config["portal"] == "Salesforce"


def test_detect_ats_greenhouse_strips_trailing_slash():
    """Trailing slash on Greenhouse URL is handled gracefully."""
    result = detect_ats("https://boards.greenhouse.io/stripe/", fetch_page=False)
    assert result is not None
    _, config = result
    assert config["token"] == "stripe"


@patch("src.job_scrapers.ats_detector.requests.get")
def test_detect_ats_page_fallback_teamtailor(mock_get):
    """Page-fetch fingerprinting detects Teamtailor via CDN URL in HTML."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = (
        "<html><head>"
        '<script src="https://assets.teamtailor-cdn.com/assets/app.js"></script>'
        "</head><body>Careers</body></html>"
    )
    mock_resp.headers = {}
    mock_resp.url = "https://careers.somecompany.com"
    mock_get.return_value = mock_resp

    result = detect_ats("https://careers.somecompany.com", fetch_page=True)
    assert result is not None
    source_name, config = result
    assert source_name == "teamtailor"
    assert "career_url" in config
