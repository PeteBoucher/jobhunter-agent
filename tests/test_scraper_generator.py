"""Tests for the AI-assisted scraper generator."""

from unittest.mock import patch

import pytest

from src.job_scrapers.scraper_generator import (
    _derive_output_path,
    _extract_candidate_api_urls,
    _extract_code,
    _extract_signals,
    generate_scraper,
)

# ── Unit tests for helper functions ──────────────────────────────────────────


def test_extract_signals_csp():
    """CSP header is captured in signals."""
    html = "<html><head></head><body></body></html>"
    headers = {"Content-Security-Policy": "default-src https://api.example.com"}
    signals = _extract_signals(html, headers, "https://example.com")
    assert "csp" in signals
    assert "api.example.com" in signals["csp"]


def test_extract_signals_script_srcs():
    """Script src attributes are extracted and resolved to absolute URLs."""
    html = '<html><head><script src="/static/app.js"></script></head></html>'
    signals = _extract_signals(html, {}, "https://example.com")
    assert any("app.js" in s for s in signals["script_srcs"])


def test_extract_signals_next_data():
    """__NEXT_DATA__ JSON blob is captured."""
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"apiUrl":"https://api.example.com"}</script>'
    )
    signals = _extract_signals(html, {}, "https://example.com")
    assert "next_data" in signals
    assert "apiUrl" in signals["next_data"]


def test_extract_signals_api_urls_in_page():
    """API-looking URLs embedded in HTML are captured."""
    html = '<html><body>fetch("https://api.careers.com/v1/jobs?page=1")</body></html>'
    signals = _extract_signals(html, {}, "https://example.com")
    assert any("api.careers.com" in u for u in signals.get("api_urls_in_page", []))


def test_extract_candidate_api_urls_from_signals():
    """API URLs from signals are returned as candidates."""
    signals = {"api_urls_in_page": ["https://api.example.com/v1/jobs"]}
    candidates = _extract_candidate_api_urls(signals, [])
    assert "https://api.example.com/v1/jobs" in candidates


def test_extract_candidate_api_urls_from_js():
    """fetch() calls in JS snippets are parsed into candidates."""
    js = "fetch('https://jobs.example.com/api/v2/listings')"
    candidates = _extract_candidate_api_urls({}, [js])
    assert "https://jobs.example.com/api/v2/listings" in candidates


def test_extract_candidate_api_urls_deduplicates():
    """Duplicate URLs across signals and JS are deduplicated."""
    url = "https://api.example.com/v1/jobs"
    signals = {"api_urls_in_page": [url, url]}
    js = f"fetch('{url}')"
    candidates = _extract_candidate_api_urls(signals, [js])
    assert candidates.count(url) == 1


def test_extract_code_strips_markdown_fence():
    """Python code inside ``` fences is extracted cleanly."""
    response = "Here is the code:\n```python\nprint('hello')\n```\n"
    code = _extract_code(response)
    assert code == "print('hello')"


def test_extract_code_no_fence_returns_stripped():
    """Response without fences is returned as-is (stripped)."""
    response = "  import requests\n\nclass MyScraper:\n    pass\n"
    code = _extract_code(response)
    assert code.startswith("import requests")


@pytest.mark.parametrize(
    "url, expected_contains",
    [
        ("https://careers.acme.com/jobs", "acme"),
        ("https://www.example.com/careers", "example"),
        ("https://jobs.netflix.com/jobs", "netflix"),
        ("https://apply.workable.com/some-company/", "workable"),
    ],
)
def test_derive_output_path_naming(url, expected_contains):
    """Output path slug is derived sensibly from the URL hostname."""
    path = _derive_output_path(url, None)
    assert expected_contains in str(path)
    assert str(path).endswith("_scraper.py")


def test_derive_output_path_explicit():
    """Explicit output_path is returned unchanged."""
    path = _derive_output_path("https://example.com", "/tmp/my_scraper.py")
    assert str(path) == "/tmp/my_scraper.py"


# ── Integration test: generate_scraper end-to-end (all HTTP mocked) ──────────


@patch("src.job_scrapers.scraper_generator._call_claude")
@patch("src.job_scrapers.scraper_generator._probe_endpoints")
@patch("src.job_scrapers.scraper_generator._scan_js_bundle")
@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_writes_file(
    mock_fetch, mock_scan, mock_probe, mock_claude, tmp_path
):
    """generate_scraper writes a file containing the generated code."""
    mock_fetch.return_value = (
        '<html><head><script src="https://example.com/app.js"></script></head></html>',
        {},
    )
    mock_scan.return_value = "fetch('https://api.example.com/v1/jobs')"
    mock_probe.return_value = [
        {"url": "https://api.example.com/v1/jobs", "status": 200, "sample": "{}"}
    ]
    mock_claude.return_value = "```python\nclass ExampleScraper:\n    pass\n```"

    out = tmp_path / "example_scraper.py"
    result_path, n_confirmed = generate_scraper(
        "https://example.com/careers", output_path=str(out)
    )

    assert result_path == str(out.resolve())
    assert n_confirmed == 1
    content = out.read_text()
    assert "AUTO-GENERATED DRAFT" in content
    assert "ExampleScraper" in content
    assert "LOW CONFIDENCE" not in content


@patch("src.job_scrapers.scraper_generator._call_claude")
@patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[])
@patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value="")
@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_no_api_found_still_calls_claude(
    mock_fetch, mock_scan, mock_probe, mock_claude, tmp_path
):
    """Generator calls Claude with no live endpoints; flags low confidence."""
    mock_fetch.return_value = ("<html><body>Careers</body></html>", {})
    mock_claude.return_value = "class FallbackScraper:\n    pass"

    out = tmp_path / "fallback_scraper.py"
    _, n_confirmed = generate_scraper(
        "https://unknown.com/careers", output_path=str(out)
    )

    mock_claude.assert_called_once()
    assert out.exists()
    assert n_confirmed == 0
    assert "LOW CONFIDENCE" in out.read_text()


def test_generate_scraper_raises_without_api_key(tmp_path, monkeypatch):
    """generate_scraper raises EnvironmentError when ANTHROPIC_API_KEY is unset."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with (
        patch(
            "src.job_scrapers.scraper_generator._fetch_page",
            return_value=("<html></html>", {}),
        ),
        patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value=""),
        patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[]),
        pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"),
    ):
        generate_scraper(
            "https://example.com/careers", output_path=str(tmp_path / "out.py")
        )
