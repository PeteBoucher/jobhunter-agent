"""AI-assisted scraper generator for novel ATS platforms.

Given a careers page URL, this module:
  1. Fetches the page and extracts ATS signals (CSP, script tags, embedded JSON)
  2. Scans JS bundles for API endpoint patterns
  3. Probes candidate endpoints to capture a live response sample
  4. Calls Claude to generate a BaseScraper subclass following project conventions
  5. Writes the draft file to src/job_scrapers/{slug}_scraper.py

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


def _fetch_page(url: str, timeout: int = 15) -> tuple:
    """Fetch a page; return (html_text, response_headers)."""
    resp = requests.get(url, timeout=timeout, headers=_HEADERS, allow_redirects=True)
    resp.raise_for_status()
    return resp.text, dict(resp.headers)


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


def _scan_js_bundle(js_url: str, timeout: int = 10) -> str:
    """Download and return up to 8KB of a JS bundle for API pattern scanning."""
    try:
        resp = requests.get(js_url, timeout=timeout, headers=_HEADERS)
        if resp.status_code == 200:
            return resp.text[:8000]
    except Exception:
        pass
    return ""


def _probe_endpoints(candidates: List[str], timeout: int = 8) -> List[Dict[str, Any]]:
    """Probe up to 3 candidate endpoints; return those that return JSON."""
    results = []
    for url in candidates[:3]:
        try:
            resp = requests.get(
                url, timeout=timeout, headers={**_HEADERS, "Accept": "application/json"}
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


# ── Claude code generation ────────────────────────────────────────────────────

_REFERENCE_SCRAPER = Path(__file__).parent / "workable_scraper.py"
_BASE_SCRAPER = Path(__file__).parent / "base_scraper.py"


def _build_prompt(
    url: str, signals: Dict, js_snippets: List[str], api_samples: List[Dict]
) -> str:
    """Build the Claude prompt for scraper generation."""
    base_src = _BASE_SCRAPER.read_text()[:3000]
    ref_src = _reference_scraper_src()

    signals_text = "\n".join(f"  {k}: {str(v)[:300]}" for k, v in signals.items() if v)
    js_text = "\n\n".join(js_snippets[:2]) if js_snippets else "(none found)"
    api_text = (
        "\n".join(
            f"  GET {s['url']}\n  Response sample: {s['sample']}" for s in api_samples
        )
        if api_samples
        else "(no live endpoints confirmed — infer from JS analysis)"
    )

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

## Requirements

1. Follow the exact same structure as the reference implementation
2. Use a dataclass for company config (like `WorkableCompany`) if multiple
   companies may share this ATS
3. Return `None` for `country` if the API doesn't include ISO2 codes —
   the base class will infer it
4. Strip HTML from description fields using a `_strip_html` helper
5. Handle pagination if the API supports it
6. `source_job_id` must be unique per company (prefix with a company slug)
7. Add a module docstring explaining the ATS name, API endpoint(s), and
   how to add new companies
8. Do NOT add the class to registry.py — leave that for the user

Output ONLY the Python source code for the new scraper file.
No explanations outside the code.
Use the filename convention: `{{ats_name}}_scraper.py`.
"""


def _reference_scraper_src() -> str:
    """Return the workable scraper source as a reference."""
    try:
        return _REFERENCE_SCRAPER.read_text()[:4000]
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


def _derive_output_path(url: str, output_path: Optional[str]) -> Path:
    """Derive a sensible output path from the URL if not specified."""
    if output_path:
        return Path(output_path)
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    # Strip generic subdomains that don't identify the company
    slug = re.sub(r"^(www|jobs|careers|work|talent|apply)\.", "", host)
    # Strip TLD exactly (no .* — avoids eating e.g. "net" inside "netflix")
    slug = re.sub(r"\.(com|io|org|net|co|uk|jobs|careers|app)$", "", slug)
    # If dots remain (e.g. "my.company.io" → "my.company"), take last segment
    if "." in slug:
        slug = slug.split(".")[-1]
    slug = re.sub(r"[^a-z0-9]+", "_", slug.lower()).strip("_")
    return Path(__file__).parent / f"{slug}_scraper.py"


# ── Public entry point ────────────────────────────────────────────────────────


def generate_scraper(url: str, output_path: Optional[str] = None) -> tuple:
    """Investigate a careers page and generate a draft scraper using Claude.

    Args:
        url: Careers page URL for the target company / ATS.
        output_path: Where to write the generated file. Auto-derived if None.

    Returns:
        (absolute_path, num_confirmed_endpoints) — callers should warn the
        user prominently when num_confirmed_endpoints is 0.

    Raises:
        requests.RequestException: If the careers page cannot be fetched.
        EnvironmentError: If ANTHROPIC_API_KEY is not set.
    """
    print(f"  Fetching {url}…")
    html, headers = _fetch_page(url)

    print("  Extracting page signals…")
    signals = _extract_signals(html, headers, url)

    # Scan first 2 script bundles for API patterns
    js_snippets: List[str] = []
    for js_url in signals.get("script_srcs", [])[:3]:
        snippet = _scan_js_bundle(js_url)
        if snippet:
            js_snippets.append(f"// {js_url}\n{snippet}")

    print("  Probing candidate API endpoints…")
    candidates = _extract_candidate_api_urls(signals, js_snippets)
    api_samples = _probe_endpoints(candidates)
    n_confirmed = len(api_samples)

    print(
        f"  Calling Claude to generate scraper… "
        f"({n_confirmed} live endpoint(s) confirmed)"
    )
    prompt = _build_prompt(url, signals, js_snippets, api_samples)
    raw_response = _call_claude(prompt)
    code = _extract_code(raw_response)

    confidence = (
        "LOW CONFIDENCE — no live API endpoints were confirmed during generation.\n"
        "# The API URL below is Claude's best guess from JS analysis only.\n"
        "# Verify the endpoint manually before registering this scraper."
        if n_confirmed == 0
        else f"Confidence: {n_confirmed} live endpoint(s) confirmed."
    )

    out_path = _derive_output_path(url, output_path)
    out_path.write_text(
        f"# AUTO-GENERATED DRAFT — review before use\n"
        f"# Generated by: job-agent scraper generate {url}\n"
        f"# {confidence}\n\n" + code
    )
    return str(out_path.resolve()), n_confirmed
