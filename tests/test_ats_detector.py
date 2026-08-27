"""Tests for ATS URL detection utility."""

from unittest.mock import MagicMock, patch

import pytest

from src.job_scrapers.ats_detector import (
    _probe_greenhouse,
    _probe_smartrecruiters,
    detect_ats,
)

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
        (
            "https://acme.recruitee.com",
            "recruitee",
            {"career_url": "https://acme.recruitee.com", "company": "Acme"},
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
    # "careers" is a generic prefix, not the company — derive from the domain
    assert config["company"] == "Somecompany"


@patch("src.job_scrapers.ats_detector.requests.get")
def test_detect_ats_page_fallback_recruitee(mock_get):
    """Page-fetch fingerprinting detects Recruitee via its CDN asset host —
    discovered via meet.zoi.tech, a custom domain with no *.recruitee.com
    in the URL at all."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = (
        "<html><head>"
        '<meta content="https://careers.recruiteecdn.com/image/upload/x.png" '
        'property="og:image"/>'
        "</head><body>Careers</body></html>"
    )
    mock_resp.headers = {}
    mock_resp.url = "https://meet.zoi.tech/"
    mock_get.return_value = mock_resp

    result = detect_ats("https://meet.zoi.tech/", fetch_page=True)
    assert result is not None
    source_name, config = result
    assert source_name == "recruitee"
    assert config["career_url"] == "https://meet.zoi.tech"
    # Regression: "meet" isn't a recognized generic careers-page prefix
    # (unlike "careers"/"jobs"), so a naive first-label heuristic picked
    # "Meet" instead of the actual company "Zoi".
    assert config["company"] == "Zoi"


@patch("src.job_scrapers.ats_detector.requests.get")
def test_detect_ats_smartrecruiters_blind_probe(mock_get):
    """Custom-domain SR site detected via blind API probe; no SR fingerprint in HTML."""
    # First call: page fetch — returns HTML with no SR fingerprints
    page_resp = MagicMock()
    page_resp.text = "<html><body>Careers at Sixt</body></html>"
    page_resp.headers = {}

    # Second call: SR probe with lowercase slug → returns jobs
    sr_resp = MagicMock()
    sr_resp.status_code = 200
    sr_resp.json.return_value = {"content": [{"name": "Some Job"}], "totalFound": 546}

    mock_get.side_effect = [page_resp, sr_resp]

    result = detect_ats("https://www.sixt.jobs/us", fetch_page=True)
    assert result is not None
    source_name, config = result
    assert source_name == "smartrecruiters"
    assert config["company_id"] == "sixt"


@pytest.mark.parametrize(
    "hostname, expected_slug",
    [
        ("www.sixt.jobs", "sixt"),
        ("jobs.acme.com", "acme"),
        ("careers.revolut.com", "revolut"),
        ("work.stripe.io", "stripe"),
    ],
)
def test_probe_smartrecruiters_slug_derivation(hostname, expected_slug):
    """_probe_smartrecruiters derives the correct slug from the hostname."""
    with patch("src.job_scrapers.ats_detector.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": [{"name": "Job"}]}
        mock_get.return_value = mock_resp

        result = _probe_smartrecruiters(hostname)
        assert result == expected_slug
        # The first probe candidate should be the lowercase slug
        first_url = mock_get.call_args_list[0][0][0]
        assert expected_slug in first_url


def test_probe_smartrecruiters_returns_none_on_empty_response():
    """_probe_smartrecruiters returns None when the API returns no content."""
    with patch("src.job_scrapers.ats_detector.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": [], "totalFound": 0}
        mock_get.return_value = mock_resp

        assert _probe_smartrecruiters("www.unknown-site.com") is None


def test_probe_smartrecruiters_returns_none_on_404():
    """_probe_smartrecruiters returns None when the API returns 404."""
    with patch("src.job_scrapers.ats_detector.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        assert _probe_smartrecruiters("www.unknown-site.com") is None


@patch("src.job_scrapers.ats_detector.requests.get")
@patch("src.job_scrapers.ats_detector._probe_smartrecruiters", return_value=None)
def test_detect_ats_greenhouse_blind_probe(mock_sr_probe, mock_get):
    """Custom-domain site (Next.js SSR proxy) detected via blind Greenhouse
    probe; no board token anywhere in client-visible HTML — the exact shape
    of careers.nebius.com, whose only client-visible Greenhouse signal is
    ai_opt_out_request links that carry a job ID, not the board token.
    SmartRecruiters probing (tried first) is stubbed out here so the mocked
    requests.get calls are only about the Greenhouse path being tested."""
    page_resp = MagicMock()
    page_resp.text = (
        "<html><body>Careers at Nebius"
        '<a href="https://greenhouse.io/ai_opt_out_request/job_post/123/ai_opt_out">'
        "opt out</a></body></html>"
    )
    page_resp.headers = {}

    gh_resp = MagicMock()
    gh_resp.status_code = 200
    gh_resp.json.return_value = {"jobs": [{"title": "Some Job"}]}

    mock_get.side_effect = [page_resp, gh_resp]

    result = detect_ats("https://careers.nebius.com/", fetch_page=True)
    assert result is not None
    source_name, config = result
    assert source_name == "greenhouse"
    assert config["token"] == "nebius"


@pytest.mark.parametrize(
    "hostname, expected_slug",
    [
        ("careers.nebius.com", "nebius"),
        ("jobs.acme.com", "acme"),
        ("careers.revolut.com", "revolut"),
    ],
)
def test_probe_greenhouse_slug_derivation(hostname, expected_slug):
    """_probe_greenhouse derives the correct slug from the hostname."""
    with patch("src.job_scrapers.ats_detector.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jobs": [{"title": "Job"}]}
        mock_get.return_value = mock_resp

        result = _probe_greenhouse(hostname)
        assert result == expected_slug
        first_url = mock_get.call_args_list[0][0][0]
        assert expected_slug in first_url


def test_probe_greenhouse_returns_none_on_empty_response():
    """_probe_greenhouse returns None when the API returns no jobs."""
    with patch("src.job_scrapers.ats_detector.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"jobs": []}
        mock_get.return_value = mock_resp

        assert _probe_greenhouse("www.unknown-site.com") is None


def test_probe_greenhouse_returns_none_on_404():
    """_probe_greenhouse returns None when the API returns 404."""
    with patch("src.job_scrapers.ats_detector.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        assert _probe_greenhouse("www.unknown-site.com") is None
