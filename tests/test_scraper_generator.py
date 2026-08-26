"""Tests for the AI-assisted scraper generator."""

from unittest.mock import patch

import pytest

from src.job_scrapers.scraper_generator import (
    _confirm_network_candidates,
    _derive_output_path,
    _detect_external_platform,
    _extract_candidate_api_urls,
    _extract_code,
    _extract_html_job_sample,
    _extract_signals,
    _import_generated_scraper,
    _is_wordpress,
    _load_base_scraper_interface,
    _wp_has_ajax_nonce,
    generate_scraper,
    run_generated_scraper_check,
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
        # Regression: a fixed TLD allowlist previously mis-derived any TLD it
        # didn't enumerate — "www.experis.es" -> "es_scraper.py" (bug).
        ("https://www.experis.es/es/buscar-trabajo", "experis"),
        ("https://career.oneflow.com/jobs", "oneflow"),
        ("https://careers.company.co.uk/jobs", "company"),
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


# ── BaseScraper interface extraction ─────────────────────────────────────────


def test_load_base_scraper_interface_includes_parse_job_schema():
    """The prompt must see _parse_job's docstring, not an arbitrary file
    slice — a fixed char cutoff previously cut off before ever reaching it,
    so Claude had no ground truth for output field names and guessed wrong
    (the generated Experis scraper used "company_name"/"published_date"
    instead of the real "company"/"posted_date" columns)."""
    text = _load_base_scraper_interface()
    assert "def _parse_job(" in text
    assert "source_job_id" in text
    assert "company" in text
    assert "posted_date" in text


def test_load_base_scraper_interface_includes_all_three_methods():
    """All three abstract methods scrapers must implement are present."""
    text = _load_base_scraper_interface()
    for method in ("_get_source_name", "_fetch_jobs", "_parse_job"):
        assert f"def {method}(" in text


# ── Live test run of a generated draft ───────────────────────────────────────

_VALID_SCRAPER_SRC = """
from typing import Any, Dict, List

from src.job_scrapers.base_scraper import BaseScraper


class FakeGeneratedScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "fake_generated"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return [{"id": 1}, {"id": 2}]

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source_job_id": str(raw_job["id"]),
            "title": "Engineer",
            "company": "Acme",
            "apply_url": "https://acme.example/jobs/" + str(raw_job["id"]),
        }
"""

# Same schema-drift bugs the generated Experis scraper actually shipped with:
# "company_name" instead of "company", and remote as a bool instead of the
# "remote"/"onsite" string enum.
_INVALID_SCRAPER_SRC = """
from typing import Any, Dict, List

from src.job_scrapers.base_scraper import BaseScraper


class BuggyGeneratedScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "buggy_generated"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return [{"id": 1}]

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source_job_id": str(raw_job["id"]),
            "title": "Engineer",
            "company_name": "Acme",
            "apply_url": "https://acme.example/jobs/1",
            "remote": True,
        }
"""

_EMPTY_FETCH_SCRAPER_SRC = """
from typing import Any, Dict, List

from src.job_scrapers.base_scraper import BaseScraper


class EmptyFetchScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "empty_fetch"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return []

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        return {}
"""

_NO_SCRAPER_CLASS_SRC = "# just a comment, no scraper class here\n"

# The actual bunq bug: a broken selector falls back to matching page
# chrome as if it were jobs, and every "job" carries the same apply_url
# (a generic listing page) because the real per-job link was never found.
# Each individual dict is schema-valid — validate_parsed_job() alone can't
# catch this; it takes validate_job_batch() looking across the sample.
_SHARED_URL_SCRAPER_SRC = """
from typing import Any, Dict, List

from src.job_scrapers.base_scraper import BaseScraper


class SharedUrlScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "shared_url"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return [{"title": "Engineer"}, {"title": "Designer"}, {"title": "Analyst"}]

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        title = raw_job["title"]
        return {
            "source_job_id": title.lower(),
            "title": title,
            "company": "Acme",
            "apply_url": "https://careers.acme.example/positions",
        }
"""


def test_import_generated_scraper_finds_the_subclass(tmp_path):
    path = tmp_path / "fake_generated_scraper.py"
    path.write_text(_VALID_SCRAPER_SRC)

    from src.job_scrapers.base_scraper import BaseScraper

    cls = _import_generated_scraper(str(path))
    assert cls.__name__ == "FakeGeneratedScraper"
    assert issubclass(cls, BaseScraper)


def test_import_generated_scraper_raises_when_no_subclass_present(tmp_path):
    path = tmp_path / "empty_scraper.py"
    path.write_text(_NO_SCRAPER_CLASS_SRC)

    with pytest.raises(ImportError, match="No BaseScraper subclass"):
        _import_generated_scraper(str(path))


@patch("src.database.get_session")
def test_run_generated_scraper_check_reports_clean_output(mock_get_session, tmp_path):
    """A well-formed generated scraper fetches, parses, and validates clean —
    never writes to the database (session.commit is never called)."""
    mock_session = mock_get_session.return_value
    path = tmp_path / "fake_generated_scraper.py"
    path.write_text(_VALID_SCRAPER_SRC)

    result = run_generated_scraper_check(str(path))

    assert result["fetch_error"] is None
    assert result["n_fetched"] == 2
    assert result["n_sampled"] == 2
    assert result["problems"] == []
    assert result["batch_problems"] == []
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


@patch("src.database.get_session")
def test_run_generated_scraper_check_flags_shared_apply_url(mock_get_session, tmp_path):
    """The bunq bug, end to end: every individual parsed dict is schema-
    valid (validate_parsed_job finds nothing), but three different-titled
    jobs sharing one generic apply_url is caught by the batch check."""
    path = tmp_path / "shared_url_scraper.py"
    path.write_text(_SHARED_URL_SCRAPER_SRC)

    result = run_generated_scraper_check(str(path))

    assert result["fetch_error"] is None
    assert result["n_sampled"] == 3
    assert result["problems"] == []
    assert len(result["batch_problems"]) == 1
    assert "apply_url" in result["batch_problems"][0]


@patch("src.database.get_session")
def test_run_generated_scraper_check_flags_schema_problems(mock_get_session, tmp_path):
    """The exact bugs the generated Experis scraper shipped with — wrong key
    name, remote as bool — are caught automatically."""
    path = tmp_path / "buggy_generated_scraper.py"
    path.write_text(_INVALID_SCRAPER_SRC)

    result = run_generated_scraper_check(str(path))

    assert result["fetch_error"] is None
    assert result["n_sampled"] == 1
    assert len(result["problems"]) == 1
    _, problems = result["problems"][0]
    assert any("company_name" in p for p in problems)
    assert any("remote" in p.lower() for p in problems)
    assert result["batch_problems"] == []  # only 1 sample, nothing to compare


@patch("src.database.get_session")
def test_run_generated_scraper_check_reports_empty_fetch(mock_get_session, tmp_path):
    path = tmp_path / "empty_fetch_scraper.py"
    path.write_text(_EMPTY_FETCH_SCRAPER_SRC)

    result = run_generated_scraper_check(str(path))

    assert result["n_fetched"] == 0
    assert "no jobs" in result["fetch_error"].lower()


def test_run_generated_scraper_check_handles_missing_file():
    """A bad path fails gracefully with a fetch_error, not an exception."""
    result = run_generated_scraper_check("/nonexistent/path/scraper.py")
    assert result["fetch_error"] is not None
    assert result["n_fetched"] == 0


# ── Headless-capture candidate confirmation ──────────────────────────────────


@patch("src.job_scrapers.scraper_generator.requests.post")
def test_confirm_network_candidates_replays_post_with_body(mock_post):
    """A captured POST call is replayed with its exact method and JSON body."""
    mock_resp = mock_post.return_value
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"jobsItems": [{"jobTitle": "Engineer"}]}

    candidates = [
        {
            "url": "https://example.com/api/services/Jobs/searchjobs",
            "method": "POST",
            "post_data": '{"filter":{"offset":0,"limit":10}}',
        }
    ]
    results = _confirm_network_candidates(candidates)

    assert len(results) == 1
    assert results[0]["method"] == "POST"
    assert results[0]["post_data"] == '{"filter":{"offset":0,"limit":10}}'
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["data"] == '{"filter":{"offset":0,"limit":10}}'


@patch("src.job_scrapers.scraper_generator.requests.get")
def test_confirm_network_candidates_skips_empty_response(mock_get):
    """A 200 response with an empty/falsy JSON body is not counted as confirmed."""
    mock_resp = mock_get.return_value
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}

    candidates = [{"url": "https://example.com/api/empty", "method": "GET"}]
    results = _confirm_network_candidates(candidates)
    assert results == []


@patch("src.job_scrapers.scraper_generator.requests.get")
def test_confirm_network_candidates_skips_non_200(mock_get):
    """A non-200 response is not counted as confirmed."""
    mock_resp = mock_get.return_value
    mock_resp.status_code = 404
    mock_resp.json.return_value = {"jobs": [1]}

    candidates = [{"url": "https://example.com/api/missing", "method": "GET"}]
    results = _confirm_network_candidates(candidates)
    assert results == []


def test_confirm_network_candidates_caps_at_five():
    """At most 5 candidates are probed, to avoid hammering the target site."""
    with patch("src.job_scrapers.scraper_generator.requests.get") as mock_get:
        mock_get.return_value.status_code = 404
        candidates = [
            {"url": f"https://example.com/api/{i}", "method": "GET"} for i in range(10)
        ]
        _confirm_network_candidates(candidates)
        assert mock_get.call_count == 5


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


@patch("src.job_scrapers.scraper_generator._capture_network_requests", return_value=[])
@patch("src.job_scrapers.scraper_generator._call_claude")
@patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[])
@patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value="")
@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_no_api_found_still_calls_claude(
    mock_fetch, mock_scan, mock_probe, mock_claude, mock_capture, tmp_path
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


@patch("src.job_scrapers.scraper_generator._capture_network_requests", return_value=[])
@patch("src.job_scrapers.scraper_generator._call_claude")
@patch("src.job_scrapers.scraper_generator._probe_endpoints", return_value=[])
@patch("src.job_scrapers.scraper_generator._probe_wordpress_rest", return_value=[])
@patch("src.job_scrapers.scraper_generator._scan_js_bundle", return_value="")
@patch("src.job_scrapers.scraper_generator._fetch_page")
def test_generate_scraper_html_mode_when_wp_rest_fails(
    mock_fetch,
    mock_scan,
    mock_wp_probe,
    mock_probe,
    mock_claude,
    mock_capture,
    tmp_path,
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
        patch(
            "src.job_scrapers.scraper_generator._capture_network_requests",
            return_value=[],
        ),
        pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"),
    ):
        generate_scraper(
            "https://example.com/careers", output_path=str(tmp_path / "out.py")
        )
