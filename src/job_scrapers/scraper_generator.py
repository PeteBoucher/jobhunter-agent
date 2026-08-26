"""AI-assisted scraper generator for novel ATS platforms.

Given a careers page URL, this module:
  1. Fetches the page and extracts ATS signals (CSP, script tags, embedded JSON)
  2. Scans JS bundles for API endpoint patterns
  3. Probes candidate endpoints (including WordPress REST paths when detected)
  4. If still no API found, renders the page in headless Chromium and captures
     the XHR/fetch calls it actually makes — the only reliable way to see the
     API on client-rendered (React/Vue/Sitecore) pages, where the job data
     never appears in the static HTML at all and the request is often a POST
     with a JSON body that static JS-source scanning can't discover
  5. If still no API found, scans the page HTML for embedded job listings
  6. Calls Claude to generate a BaseScraper subclass following project conventions
  7. Writes the draft file to src/job_scrapers/{slug}_scraper.py

The output is intentionally marked as a draft — it must be reviewed, linted,
and test-scraped before being added to the registry.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests

# ── Page analysis ─────────────────────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_page(url: str, timeout: int = 15, verify: bool = True) -> tuple:
    """Fetch a page; return (html_text, response_headers, final_url).

    final_url is the URL after following any redirects — used to detect when
    a careers page hands off to an external job platform.
    """
    resp = requests.get(
        url, timeout=timeout, headers=_HEADERS, allow_redirects=True, verify=verify
    )
    resp.raise_for_status()
    return resp.text, dict(resp.headers), resp.url


def _extract_signals(
    html: str, headers: Dict[str, str], base_url: str
) -> Dict[str, Any]:
    """Extract ATS signals from page HTML and response headers."""
    signals: Dict[str, Any] = {}

    # CSP header — often reveals backend API domains
    csp = headers.get("Content-Security-Policy", "") or headers.get(
        "content-security-policy", ""
    )
    if csp:
        signals["csp"] = csp[:800]

    # Script src URLs
    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
    signals["script_srcs"] = [urljoin(base_url, s) for s in script_srcs]

    # Embedded JSON blobs (__NEXT_DATA__, __NUXT__, runtimeConfig)
    for pattern, key in [
        (r'id="__NEXT_DATA__"[^>]*>(\{.+?\})</script>', "next_data"),
        (r"__NUXT__\s*=\s*(\{.+?\})", "nuxt_data"),
        (r"window\.__NUXT__\.config\s*=\s*(\{.+?\})", "nuxt_config"),
        (r"window\.__app_config\s*=\s*(\{.+?\})", "app_config"),
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            signals[key] = m.group(1)[:1000]

    # Raw URLs that look like API endpoints
    api_urls = re.findall(
        r"https?://[a-z0-9._-]+/(?:api|v\d)[a-zA-Z0-9._/\-?=&%]*", html
    )
    signals["api_urls_in_page"] = list(set(api_urls))[:20]

    return signals


def _scan_js_bundle(js_url: str, timeout: int = 10, verify: bool = True) -> str:
    """Download and return up to 8KB of a JS bundle for API pattern scanning."""
    try:
        resp = requests.get(js_url, timeout=timeout, headers=_HEADERS, verify=verify)
        if resp.status_code == 200:
            return resp.text[:8000]
    except Exception:
        pass
    return ""


def _probe_endpoints(
    candidates: List[str], timeout: int = 8, verify: bool = True
) -> List[Dict[str, Any]]:
    """Probe up to 3 candidate endpoints; return those that return JSON."""
    results = []
    for url in candidates[:3]:
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={**_HEADERS, "Accept": "application/json"},
                verify=verify,
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    results.append(
                        {"url": url, "status": 200, "sample": str(data)[:600]}
                    )
                except Exception:
                    pass
        except Exception:
            pass
    return results


def _extract_candidate_api_urls(
    signals: Dict[str, Any], js_snippets: List[str]
) -> List[str]:
    """Build a list of candidate API endpoint URLs to probe."""
    candidates = list(signals.get("api_urls_in_page", []))

    # Look in JS snippets for fetch/axios calls
    for snippet in js_snippets:
        found = re.findall(
            r'(?:fetch|axios\.get|axios\.post)\s*\(\s*["`\']([^"`\']+)["`\']',
            snippet,
        )
        candidates.extend(found)

        # Also find URL construction patterns
        base_matches = re.findall(
            r'(?:baseURL|apiUrl|api_url)["\s:=]+["`\'](https?://[^"`\']+)["`\']',
            snippet,
            re.I,
        )
        candidates.extend(base_matches)

    # Deduplicate and keep only HTTP(S) URLs
    seen = set()
    result = []
    for u in candidates:
        if u.startswith("http") and u not in seen:
            seen.add(u)
            result.append(u)
    return result


# ── WordPress detection ───────────────────────────────────────────────────────

# Common WP REST API paths used by job listing plugins
_WP_JOB_REST_PATHS = [
    "/wp-json/wp/v2/jobs",
    "/wp-json/wp/v2/job-listings",  # WP Job Manager plugin
    "/wp-json/wp/v2/openings",
    "/wp-json/wp/v2/careers",
    "/wp-json/jobs/v1/listings",
]


def _is_wordpress(html: str) -> bool:
    return "wp-content" in html or "wp-admin" in html or "wp-json" in html


def _wp_has_ajax_nonce(html: str) -> bool:
    """Return True if the page uses WordPress AJAX with a per-session nonce.

    This pattern (admin-ajax.php + nonce) is not automatable without a
    headless browser — the nonce changes every page load.
    """
    return "admin-ajax.php" in html and bool(
        re.search(r'"nonce"\s*:\s*"[a-f0-9]+"', html)
    )


def _probe_wordpress_rest(
    base_url: str, timeout: int = 8, verify: bool = True
) -> List[Dict[str, Any]]:
    """Probe known WordPress REST API paths for job listings."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    results = []
    for path in _WP_JOB_REST_PATHS:
        url = root + path
        try:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={**_HEADERS, "Accept": "application/json"},
                verify=verify,
            )
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    # Only count as confirmed if the response has content
                    if data and (isinstance(data, list) and len(data) > 0):
                        results.append(
                            {"url": url, "status": 200, "sample": str(data)[:600]}
                        )
                except Exception:
                    pass
        except Exception:
            pass
    return results


# ── Headless-browser network capture ────────────────────────────────────────
#
# Static requests.get() only ever sees the initial HTML response. Many career
# sites are client-rendered (React/Vue/Sitecore, etc.) and populate the page
# entirely via a fetch/XHR call after load — the job data never appears in
# the static HTML or in a literal string in the JS bundle, so no amount of
# regex scanning over static content can find it. Rendering the page for
# real and recording what it actually calls is the only reliable way in.

# Third-party analytics/tracking/chat/consent noise seen alongside real APIs
# on client-rendered pages — never job data, so never worth probing.
_IGNORED_NETWORK_HOST_RE = re.compile(
    r"google-analytics\.com|googletagmanager\.com|doubleclick\.net|"
    r"hubspot\.com|hsforms\.com|hs-scripts\.com|hsappstatic\.net|hubapi\.com|"
    r"cta-service|hscta\.net|"
    r"linkedin\.com|cookielaw\.org|onetrust\.com|"
    r"facebook\.com/tr|clarity\.ms|sentry\.io|hotjar\.com|segment\.(io|com)|"
    r"intercom\.io|maps\.googleapis\.com|fonts\.g(oogle|static)\.com",
    re.I,
)


def _capture_network_requests(
    url: str, timeout: int = 25, verify: bool = True
) -> List[Dict[str, Any]]:
    """Render the page in headless Chromium and record its XHR/fetch calls.

    Returns a list of {"url", "method", "post_data"} dicts, restricted to
    same-site requests (registrable domain match) with tracking/analytics
    noise filtered out. Requires the `playwright` package and its browser
    binaries (`playwright install chromium`) — raises ImportError/ RuntimeError
    if unavailable, which callers should treat as "capture unavailable", not
    a hard failure of the whole generation run.
    """
    from playwright.sync_api import sync_playwright

    captured: List[Dict[str, Any]] = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--ignore-certificate-errors"] if not verify else [],
        )
        try:
            context = browser.new_context(
                ignore_https_errors=not verify,
                user_agent=_HEADERS["User-Agent"],
            )
            page = context.new_page()

            def on_request(req: Any) -> None:
                if req.resource_type in ("xhr", "fetch") and req.url not in seen_urls:
                    seen_urls.add(req.url)
                    captured.append(
                        {
                            "url": req.url,
                            "method": req.method,
                            "post_data": req.post_data,
                        }
                    )

            page.on("request", on_request)
            try:
                # "domcontentloaded" instead of "networkidle": pages with a
                # chat widget or other persistent polling (HubSpot, Intercom,
                # etc.) never go network-idle, which made this raise before
                # a single request was captured. A fixed settle-time wait
                # below is what actually lets client-rendered apps fetch
                # their data.
                page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            except Exception:
                pass
            page.wait_for_timeout(5000)
        finally:
            browser.close()

    host = urlparse(url).hostname or ""
    registrable = ".".join(host.split(".")[-2:]) if "." in host else host
    same_site = []
    for c in captured:
        c_host = urlparse(c["url"]).hostname or ""
        if (
            registrable
            and registrable in c_host
            and not _IGNORED_NETWORK_HOST_RE.search(c["url"])
        ):
            same_site.append(c)
    return same_site


def _confirm_network_candidates(
    candidates: List[Dict[str, Any]], timeout: int = 8, verify: bool = True
) -> List[Dict[str, Any]]:
    """Replay captured XHR/fetch calls with `requests` (no browser session)
    to confirm they're live outside the browser and return real content."""
    results = []
    for c in candidates[:5]:
        method = (c.get("method") or "GET").upper()
        url = c["url"]
        post_data = c.get("post_data")
        headers = {**_HEADERS, "Accept": "application/json"}
        try:
            if method == "POST":
                if post_data:
                    headers["Content-Type"] = "application/json"
                resp = requests.post(
                    url, data=post_data, timeout=timeout, headers=headers, verify=verify
                )
            else:
                resp = requests.get(
                    url, timeout=timeout, headers=headers, verify=verify
                )
            if resp.status_code != 200:
                continue
            data = resp.json()
        except Exception:
            continue
        if not data:
            continue
        results.append(
            {
                "url": url,
                "method": method,
                "post_data": post_data,
                "status": 200,
                "sample": str(data)[:600],
            }
        )
    return results


# ── External platform detection ──────────────────────────────────────────────

# Job-specific URL patterns for platforms we cannot scrape.
# Social-media footer links (linkedin.com/company/acme with no /jobs suffix)
# are intentionally excluded — only job-listing paths trigger the bail-out.
_EXTERNAL_JOB_PLATFORMS = [
    (
        re.compile(r"linkedin\.com/(jobs|company/[^/?#]+/jobs)", re.I),
        "LinkedIn",
        "LinkedIn jobs cannot be scraped without their API. "
        "Check if the company also posts on a supported ATS "
        "(Greenhouse, Lever, Ashby, Workable, etc.).",
    ),
    (
        re.compile(r"indeed\.com/(cmp/[^/?#]+/jobs|viewjob|jobs\?)", re.I),
        "Indeed",
        "Indeed jobs cannot be scraped directly. "
        "Check if the company posts on a supported ATS.",
    ),
    (
        re.compile(r"glassdoor\.com/Jobs/", re.I),
        "Glassdoor",
        "Glassdoor jobs cannot be scraped directly. "
        "Check if the company posts on a supported ATS.",
    ),
]


def _detect_external_platform(html: str, final_url: str) -> Optional[tuple]:
    """Return (platform_name, help_note) if the page hands off to an unsupported
    external job platform, or None if it looks self-hosted.

    Checks the final URL first (redirect is the clearest signal), then looks
    for job-specific href links in the page HTML.
    """
    for pattern, platform, note in _EXTERNAL_JOB_PLATFORMS:
        if pattern.search(final_url):
            return platform, note

    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html, re.I)
    for pattern, platform, note in _EXTERNAL_JOB_PLATFORMS:
        if any(pattern.search(h) for h in hrefs):
            return platform, note

    return None


# ── HTML job extraction (fallback when no API found) ─────────────────────────

_JOB_CLASS_RE = re.compile(
    r"\b(job|position|opening|vacancy|career|role|listing|employment)\b", re.I
)


def _extract_html_job_sample(html: str) -> Optional[str]:
    """Find job-like container elements in the page HTML.

    Handles two patterns:
    - Block elements (div/article/li/section) with job-related CSS classes
      + heading + link
    - Table rows (tr with a class + a link) — SAP SuccessFactors, Taleo, and
      similar HR portals that render listings as HTML tables

    Returns HTML of up to 2 representative blocks, or None if nothing is found.
    """
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        candidates = []

        # Block elements with job-related class names containing a heading and link
        for tag in soup.find_all(["div", "article", "li", "section"]):
            classes = " ".join(tag.get("class", []))
            if not _JOB_CLASS_RE.search(classes):
                continue
            if tag.find(["h1", "h2", "h3", "h4"]) and tag.find("a"):
                candidates.append(tag)

        # Table rows: many HR portals (SAP SF, Taleo) render listings as <tr> rows.
        # Don't require a heading — table rows use <td> cells, not <h3> tags.
        # Require at least 3 matching rows to avoid false positives (nav tables, etc.)
        if not candidates:
            tr_candidates = [
                tr
                for tr in soup.find_all("tr")
                if tr.get("class") and tr.find("a", href=True)
            ]
            if len(tr_candidates) >= 3:
                candidates = tr_candidates

        if not candidates:
            return None

        parts = [str(c)[:1200] for c in candidates[:2]]
        return "\n\n<!-- next job block -->\n\n".join(parts)
    except Exception:
        return None


# ── Claude code generation ────────────────────────────────────────────────────

_REFERENCE_API_SCRAPER = Path(__file__).parent / "workable_scraper.py"
_REFERENCE_HTML_SCRAPER = Path(__file__).parent / "innovairv_scraper.py"
_BASE_SCRAPER = Path(__file__).parent / "base_scraper.py"

_INTERFACE_METHODS = ("_get_source_name", "_fetch_jobs", "_parse_job")


def _load_base_scraper_interface() -> str:
    """Extract the BaseScraper abstract method signatures + docstrings.

    Used instead of a raw `base_scraper.py` file-slice: a fixed character
    cutoff was cutting off mid-file, in an unrelated regex table, well
    before ever reaching `_parse_job`'s docstring — the actual output
    schema. Claude had no ground truth for field names and had to guess,
    which is exactly what produced the generated Experis scraper's
    "company_name"/"published_date" instead of the real "company"/
    "posted_date" columns. Extracting via `ast` instead of copy-pasting the
    schema into this prompt template keeps the two from drifting apart
    again — the docstring on `_parse_job` in base_scraper.py is the single
    source of truth, and whatever it says is what Claude sees.
    """
    import ast

    tree = ast.parse(_BASE_SCRAPER.read_text())
    parts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "BaseScraper":
            for item in node.body:
                if (
                    isinstance(item, ast.FunctionDef)
                    and item.name in _INTERFACE_METHODS
                ):
                    args = [a.arg for a in item.args.args]
                    if item.args.kwarg:
                        args.append(f"**{item.args.kwarg.arg}")
                    doc = ast.get_docstring(item) or ""
                    parts.append(
                        f'def {item.name}({", ".join(args)}):\n    """{doc}"""'
                    )
            break
    return "\n\n".join(parts)


def _build_prompt(
    url: str,
    signals: Dict,
    js_snippets: List[str],
    api_samples: List[Dict],
    html_job_sample: Optional[str] = None,
) -> str:
    """Build the Claude prompt for scraper generation."""
    base_src = _load_base_scraper_interface()

    # Choose reference implementation based on scraping mode
    use_html_mode = html_job_sample is not None and not api_samples
    ref_src = _reference_scraper_src(html_mode=use_html_mode)

    signals_text = "\n".join(f"  {k}: {str(v)[:300]}" for k, v in signals.items() if v)
    js_text = "\n\n".join(js_snippets[:2]) if js_snippets else "(none found)"

    if api_samples:
        lines = []
        for s in api_samples:
            line = f"  {s.get('method', 'GET')} {s['url']}"
            if s.get("post_data"):
                line += f"\n  Request body: {s['post_data']}"
            line += f"\n  Response sample: {s['sample']}"
            lines.append(line)
        api_text = "\n\n".join(lines)
    elif html_job_sample:
        api_text = "(no live REST API endpoints found)"
    else:
        api_text = "(no live endpoints confirmed — infer from JS analysis)"

    html_section = ""
    if use_html_mode:
        html_section = f"""
### Job listings found embedded in the page HTML

The careers page contains job listings directly in its HTML — there is no
REST API to call. Use BeautifulSoup to scrape the page.

Representative job block(s) from the page (use these to determine the correct
CSS selectors):

```html
{html_job_sample}
```

**Requirements for HTML mode:**
- Fetch the careers page URL with `requests`
- Parse with `BeautifulSoup(resp.text, "html.parser")`
- Use `soup.select()` with the exact CSS selectors visible in the HTML above
- Derive `source_job_id` from the job detail URL slug (last path segment) if
  links to individual job pages exist, otherwise slugify the title
- Do NOT generate code that calls any REST API — use HTML parsing only
"""

    wp_nonce_warning = ""
    if signals.get("warning_wp_ajax_nonce"):
        wp_nonce_warning = f"""
### ⚠ WordPress AJAX + nonce detected
{signals["warning_wp_ajax_nonce"]}
"""

    return f"""You are generating a Python job scraper for the jobhunter-agent project.

## Task

Write a complete BaseScraper subclass for the careers site at:
  {url}

## BaseScraper ABC (implement these 3 methods):

```python
{base_src}
```

## Reference implementation (follow this pattern exactly):

```python
{ref_src}
```

## Evidence collected from the target site

### Page signals (CSP, embedded JSON, script URLs):
{signals_text}

### JS bundle excerpts (API endpoint patterns):
{js_text}

### Live API responses:
{api_text}
{html_section}{wp_nonce_warning}
## Requirements

1. Follow the exact same structure as the reference implementation
2. Use a dataclass for company config (like `WorkableCompany`) only if multiple
   companies share this ATS — for single-company sites, hardcode the details
3. Return `None` for `country` if the data doesn't include ISO2 codes —
   the base class will infer it
4. Strip HTML from description fields using a `_strip_html` helper or BeautifulSoup
5. Handle pagination if supported
6. `source_job_id` must be stable across runs (URL slug preferred over position index)
7. Add a module docstring explaining the site, scraping approach, and page structure
8. Do NOT add the class to registry.py — leave that for the user
9. If a "Live API responses" entry above shows a method other than GET (e.g. POST),
   the request MUST use that method and send the exact request body shown (as JSON) —
   do not silently convert it to a GET or drop the body

Output ONLY the Python source code for the new scraper file.
No explanations outside the code.
Use the filename convention: `{{ats_name}}_scraper.py`.
"""


def _reference_scraper_src(html_mode: bool = False) -> str:
    """Return the appropriate reference scraper source."""
    path = _REFERENCE_HTML_SCRAPER if html_mode else _REFERENCE_API_SCRAPER
    try:
        return path.read_text()[:4000]
    except Exception:
        # Fall back to the other reference if primary is unavailable
        try:
            fallback = _REFERENCE_API_SCRAPER if html_mode else _REFERENCE_HTML_SCRAPER
            return fallback.read_text()[:4000]
        except Exception:
            return "(reference scraper not available)"


def _call_claude(prompt: str) -> str:
    """Call Claude Haiku to generate the scraper code."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. Export it before running scraper generate."
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    block = message.content[0]
    assert hasattr(
        block, "text"
    ), f"Unexpected Claude response block type: {type(block)}"
    return block.text


def _extract_code(response: str) -> str:
    """Extract Python code from Claude's response (strips markdown fences)."""
    m = re.search(r"```python\n(.*?)```", response, re.DOTALL)
    if m:
        return m.group(1).strip()
    # No fence — assume the whole response is code
    return response.strip()


# Second-level labels that indicate a two-label public suffix (e.g. "co.uk",
# "com.au") — when present, the company label is one further back.
_TWO_LABEL_SUFFIX_INDICATORS = {"co", "com", "org", "net", "gov", "ac", "edu"}


def _company_label_from_host(host: str) -> str:
    """Derive the company label from a hostname without a hardcoded TLD list.

    Strips generic careers-page subdomain prefixes, then takes the label
    immediately before the public suffix — "career.oneflow.com" -> "oneflow",
    "careers.company.co.uk" -> "company", "my.company.io" -> "company".
    A fixed TLD allowlist (the previous approach) silently mis-derives any
    TLD it doesn't enumerate, e.g. "www.experis.es" -> "es".
    """
    stripped = re.sub(
        r"^(www|jobs|careers|career|work|talent|apply)\.", "", host, flags=re.I
    )
    labels = stripped.split(".")
    if len(labels) >= 3 and labels[-2].lower() in _TWO_LABEL_SUFFIX_INDICATORS:
        return labels[-3]
    if len(labels) >= 2:
        return labels[-2]
    return labels[0]


def _derive_output_path(url: str, output_path: Optional[str]) -> Path:
    """Derive a sensible output path from the URL if not specified."""
    if output_path:
        return Path(output_path)
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    slug = _company_label_from_host(host)
    slug = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
    return Path(__file__).parent / f"{slug}_scraper.py"


# ── Public entry point ────────────────────────────────────────────────────────


def generate_scraper(
    url: str, output_path: Optional[str] = None, insecure: bool = False
) -> tuple:
    """Investigate a careers page and generate a draft scraper using Claude.

    Args:
        url: Careers page URL for the target company / ATS.
        output_path: Where to write the generated file. Auto-derived if None.
        insecure: Skip TLS certificate verification. Only use this for sites
            with a known server-side cert chain misconfiguration (e.g. a
            missing intermediate) — it disables verification for every
            request this function makes against the target host.

    Returns:
        (absolute_path, num_confirmed_endpoints) — callers should warn the
        user prominently when num_confirmed_endpoints is 0.

    Raises:
        requests.RequestException: If the careers page cannot be fetched.
        EnvironmentError: If ANTHROPIC_API_KEY is not set.
    """
    verify = not insecure
    if insecure:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"  Fetching {url}…")
    html, headers, final_url = _fetch_page(url, verify=verify)

    # Bail out immediately for platforms we cannot scrape
    ext = _detect_external_platform(html, final_url)
    if ext:
        platform, note = ext
        raise RuntimeError(
            f"This careers page uses {platform} for job listings, which cannot "
            f"be scraped directly.\n{note}"
        )

    print("  Extracting page signals…")
    signals = _extract_signals(html, headers, url)

    # Scan first 3 script bundles for API patterns
    js_snippets: List[str] = []
    for js_url in signals.get("script_srcs", [])[:3]:
        snippet = _scan_js_bundle(js_url, verify=verify)
        if snippet:
            js_snippets.append(f"// {js_url}\n{snippet}")

    print("  Probing candidate API endpoints…")
    candidates = _extract_candidate_api_urls(signals, js_snippets)
    api_samples = _probe_endpoints(candidates, verify=verify)

    # WordPress fallback: try known WP REST job paths when no API found yet
    if not api_samples and _is_wordpress(html):
        print("  WordPress site — probing WP REST API job endpoints…")
        wp_samples = _probe_wordpress_rest(url, verify=verify)
        if wp_samples:
            api_samples.extend(wp_samples)
            print(f"  Found {len(wp_samples)} WP REST endpoint(s)")

        # Warn Claude about the AJAX+nonce pattern if present
        if _wp_has_ajax_nonce(html):
            signals["warning_wp_ajax_nonce"] = (
                "Page uses WordPress AJAX (admin-ajax.php) with a per-session nonce. "
                "This endpoint requires a fresh nonce from a browser session and "
                "cannot be called directly. Use HTML scraping instead."
            )

    # Headless-browser fallback: static requests.get() never sees API calls
    # made by client-rendered pages (React/Vue/Sitecore, etc.) — render the
    # page for real and see what it actually fetches.
    if not api_samples:
        print(
            "  No API found via static analysis — "
            "rendering page in headless Chromium to capture real network calls…"
        )
        try:
            network_log = _capture_network_requests(final_url or url, verify=verify)
            browser_samples = _confirm_network_candidates(network_log, verify=verify)
            if browser_samples:
                api_samples.extend(browser_samples)
                print(
                    f"  Found {len(browser_samples)} endpoint(s) via headless capture"
                )
            else:
                print("  No confirmed endpoints from headless capture")
        except Exception as e:
            print(f"  ⚠ Headless capture unavailable/failed: {e}")

    n_confirmed = len(api_samples)

    # No API at all: look for job content embedded in the page HTML
    html_job_sample: Optional[str] = None
    if n_confirmed == 0:
        print("  No API found — scanning page HTML for embedded job listings…")
        html_job_sample = _extract_html_job_sample(html)
        if html_job_sample:
            print("  Job HTML elements found — generating HTML scraper")
        else:
            print("  No recognisable job HTML found — Claude will infer the approach")

    print(
        f"  Calling Claude to generate scraper… "
        f"({n_confirmed} live endpoint(s) confirmed)"
    )
    prompt = _build_prompt(url, signals, js_snippets, api_samples, html_job_sample)
    raw_response = _call_claude(prompt)
    code = _extract_code(raw_response)

    if n_confirmed == 0 and html_job_sample:
        confidence = (
            "LOW CONFIDENCE (HTML scraper) — no REST API was found.\n"
            "# Generated from page HTML structure. Verify selectors before registering."
        )
    elif n_confirmed == 0:
        confidence = (
            "LOW CONFIDENCE — no live API endpoints were confirmed during generation.\n"
            "# The API URL below is Claude's best guess from JS analysis only.\n"
            "# Verify the endpoint manually before registering this scraper."
        )
    else:
        confidence = f"Confidence: {n_confirmed} live endpoint(s) confirmed."

    out_path = _derive_output_path(url, output_path)
    out_path.write_text(
        f"# AUTO-GENERATED DRAFT — review before use\n"
        f"# Generated by: job-agent scraper generate {url}\n"
        f"# {confidence}\n\n" + code
    )
    return str(out_path.resolve()), n_confirmed
