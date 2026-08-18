"""Tests for the AI-assisted scraper generator."""

from unittest.mock import patch

import pytest

from src.job_scrapers.scraper_generator import (
    _derive_output_path,
    _detect_external_platform,
    _extract_candidate_api_urls,
    _extract_code,
    _extract_html_job_sample,
    _extract_signals,
    _is_wordpress,
    _wp_has_ajax_nonce,
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
        "https://example.com/careers",
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
    mock_fetch.return_value = (
        "<html><body>Careers</body></html>",
        {},
        "https://unknown.com/careers",
    )
    mock_claude.return_value = "class FallbackScraper:\n    pass"

    out = tmp_path / "fallback_scraper.py"
    _, n_confirmed = generate_scraper(
        "https://unknown.com/careers", output_path=str(out)
    )

    mock_claude.assert_called_once()
    assert out.exists()
    assert n_confirmed == 0
    assert "LOW CONFIDENCE" in out.read_text()


# ── WordPress detection helpers ───────────────────────────────────────────────


def test_is_wordpress_detects_wp_content():
    """HTML with wp-content is identified as WordPress."""
    assert _is_wordpress(
        '<link rel="stylesheet" href="/wp-content/themes/main/style.css">'
    )


def test_is_wordpress_detects_wp_json():
    """HTML with wp-json reference is identified as WordPress."""
    assert _is_wordpress('{"url":"https://example.com/wp-json/wp/v2"}')


def test_is_wordpress_false_for_plain_html():
    """Plain HTML with no WordPress indicators is not flagged."""
    assert not _is_wordpress("<html><body><div class='jobs'>Hello</div></body></html>")


def test_wp_has_ajax_nonce_detects_nonce():
    """Page using admin-ajax.php with a nonce is flagged."""
    html = 'var config = {"nonce": "a1b2c3d4", "ajaxUrl": "/wp-admin/admin-ajax.php"};'
    assert _wp_has_ajax_nonce(html)


def test_wp_has_ajax_nonce_returns_false_without_nonce():
    """Page with admin-ajax.php but no nonce is not flagged."""
    html = 'var ajaxUrl = "/wp-admin/admin-ajax.php";'
    assert not _wp_has_ajax_nonce(html)


def test_wp_has_ajax_nonce_returns_false_without_ajax():
    """Page with nonce but no admin-ajax.php is not flagged."""
    html = 'var config = {"nonce": "a1b2c3d4"};'
    assert not _wp_has_ajax_nonce(html)


# ── HTML job sample extraction ────────────────────────────────────────────────


def test_extract_html_job_sample_finds_job_divs():
    """Divs with job-like class names containing headings + links are extracted."""
    html = """
    <html><body>
      <div class="job-listing">
        <h3>Software Engineer</h3>
        <p>Join our team.</p>
        <a href="/jobs/software-engineer">Apply</a>
      </div>
      <div class="job-listing">
        <h3>Product Manager</h3>
        <p>Lead product.</p>
        <a href="/jobs/product-manager">Apply</a>
      </div>
    </body></html>
    """
    sample = _extract_html_job_sample(html)
    assert sample is not None
    assert "Software Engineer" in sample or "Product Manager" in sample


def test_extract_html_job_sample_returns_none_without_job_elements():
    """HTML with no job-like elements returns None."""
    html = "<html><body><div class='content'><p>Welcome</p></div></body></html>"
    sample = _extract_html_job_sample(html)
    assert sample is None


def test_extract_html_job_sample_requires_heading_and_link():
    """Container with job class but no heading+link pair is skipped."""
    html = """
    <html><body>
      <div class="job-listing">
        <p>Some text without a heading or apply link.</p>
      </div>
    </body></html>
    """
    sample = _extract_html_job_sample(html)
    assert sample is None


def test_extract_html_job_sample_finds_table_rows():
    """Table rows with a class and a link are extracted (SAP SuccessFactors pattern)."""
    html = """
    <html><body><table>
      <tr id="header"><th>Title</th><th>Location</th></tr>
      <tr class="data-row"><td><a href="/job/eng/123/">Engineer</a></td>
        <td>Madrid, ES</td></tr>
      <tr class="data-row"><td><a href="/job/pm/456/">PM</a></td>
        <td>London, GB</td></tr>
      <tr class="data-row"><td><a href="/job/dev/789/">Developer</a></td>
        <td>Berlin, DE</td></tr>
    </table></body></html>
    """
    sample = _extract_html_job_sample(html)
    assert sample is not None
    assert "data-row" in sample
    assert "Engineer" in sample or "Product Manager" in sample


def test_extract_html_job_sample_ignores_sparse_table_rows():
    """Fewer than 3 table rows are not treated as a job listing (avoids nav tables)."""
    html = """
    <html><body><table>
      <tr class="nav-item"><td><a href="/about">About</a></td></tr>
      <tr class="nav-item"><td><a href="/contact">Contact</a></td></tr>
    </table></body></html>
    """
    sample = _extract_html_job_sample(html)
    assert sample is None


def test_extract_html_job_sample_limits_to_two_blocks():
    """At most 2 job blocks are returned even if more exist."""
    blocks = "".join(
        f'<div class="job-item"><h3>Job {i}</h3><a href="/jobs/{i}">Apply</a></div>'
        for i in range(5)
    )
    html = f"<html><body>{blocks}</body></html>"
    sample = _extract_html_job_sample(html)
    assert sample is not None
    # The separator only appears between blocks, so max once for 2 blocks
    assert sample.count("<!-- next job block -->") <= 1


# ── WordPress REST probe integration ─────────────────────────────────────────


@patch("src.job_scrapers.scraper_generator._call_claude")
@patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[])
@patch("src.job_scrapers.scraper_generator._probe_wordpress_rest")
@patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value="")
@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_probes_wp_rest_on_wordpress_site(
    mock_fetch, mock_scan, mock_wp_probe, mock_probe, mock_claude, tmp_path
):
    """WordPress sites trigger WP REST API probing as a fallback."""
    wp_html = '<html><head><link href="/wp-content/themes/main.css"></head></html>'
    mock_fetch.return_value = (wp_html, {}, "https://example.com/careers")
    mock_wp_probe.return_value = [
        {
            "url": "https://example.com/wp-json/wp/v2/jobs",
            "status": 200,
            "sample": "[{}]",
        }
    ]
    mock_claude.return_value = "class WpScraper:\n    pass"

    out = tmp_path / "wp_scraper.py"
    _, n_confirmed = generate_scraper(
        "https://example.com/careers", output_path=str(out)
    )

    mock_wp_probe.assert_called_once()
    assert n_confirmed == 1
    assert "LOW CONFIDENCE" not in out.read_text()


@patch("src.job_scrapers.scraper_generator._call_claude")
@patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[])
@patch("src.job_scrapers.scraper_generator._probe_wordpress_rest", return_value=[])
@patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value="")
@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_html_mode_when_wp_rest_fails(
    mock_fetch, mock_scan, mock_wp_probe, mock_probe, mock_claude, tmp_path
):
    """WordPress site with no REST endpoints falls through to HTML scraping mode."""
    wp_html = """
    <html>
      <head><link href="/wp-content/themes/main.css"></head>
      <body>
        <div class="job-listing"><h3>Engineer</h3><a href="/jobs/eng">Apply</a></div>
      </body>
    </html>
    """
    mock_fetch.return_value = (wp_html, {}, "https://example.com/careers")
    mock_claude.return_value = "class HtmlScraper:\n    pass"

    out = tmp_path / "html_scraper.py"
    _, n_confirmed = generate_scraper(
        "https://example.com/careers", output_path=str(out)
    )

    assert n_confirmed == 0
    content = out.read_text()
    assert "LOW CONFIDENCE" in content
    assert "HTML scraper" in content


# ── External platform detection ───────────────────────────────────────────────


def test_detect_external_platform_linkedin_redirect():
    """Final URL on LinkedIn jobs triggers detection."""
    result = _detect_external_platform(
        "<html></html>",
        "https://www.linkedin.com/company/acme/jobs",
    )
    assert result is not None
    platform, _ = result
    assert platform == "LinkedIn"


def test_detect_external_platform_linkedin_href():
    """Page linking to LinkedIn /company/.../jobs triggers detection."""
    html = '<a href="https://www.linkedin.com/company/lognext/jobs">View jobs</a>'
    result = _detect_external_platform(html, "https://www.lognext.com/en/work-with-us/")
    assert result is not None
    platform, _ = result
    assert platform == "LinkedIn"


def test_detect_external_platform_social_link_only():
    """Plain LinkedIn social link (no /jobs path) does not trigger detection."""
    html = '<a href="https://www.linkedin.com/company/acme">Follow us</a>'
    result = _detect_external_platform(html, "https://acme.com/careers")
    assert result is None


def test_detect_external_platform_self_hosted():
    """A standard careers page with no external platform links returns None."""
    html = '<div class="job"><h3>Engineer</h3><a href="/jobs/eng">Apply</a></div>'
    result = _detect_external_platform(html, "https://careers.acme.com/jobs")
    assert result is None


@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_raises_on_linkedin_redirect(mock_fetch, tmp_path):
    """generate_scraper raises RuntimeError when the page redirects to LinkedIn."""
    mock_fetch.return_value = (
        "<html><body>Redirecting…</body></html>",
        {},
        "https://www.linkedin.com/company/acme/jobs",
    )
    with pytest.raises(RuntimeError, match="LinkedIn"):
        generate_scraper(
            "https://acme.com/work-with-us",
            output_path=str(tmp_path / "out.py"),
        )


def test_generate_scraper_raises_without_api_key(tmp_path, monkeypatch):
    """generate_scraper raises EnvironmentError when ANTHROPIC_API_KEY is unset."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with (
        patch(
            "src.job_scrapers.scraper_generator._fetch_page",
            return_value=("<html></html>", {}, "https://example.com/careers"),
        ),
        patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value=""),
        patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[]),
        pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"),
    ):
        generate_scraper(
            "https://example.com/careers", output_path=str(tmp_path / "out.py")
        )
