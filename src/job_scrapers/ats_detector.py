"""ATS platform detection from a careers URL.

Given a URL (or a careers page URL), returns the source_name and a config dict
suitable for inserting into the scraper_config table.

Detection is URL-pattern-first; for ambiguous URLs a page fetch checks CSP
headers, script src tags, and page content for known ATS fingerprints.

Supported ATS platforms (i.e. platforms we already have scrapers for):

  greenhouse      boards.greenhouse.io / job-boards.greenhouse.io
  lever           jobs.lever.co / lever.co
  ashby           app.ashbyhq.com / jobs.ashbyhq.com
  workday         *.wd{N}.myworkdayjobs.com
  smartrecruiters jobs.smartrecruiters.com / smartrecruiters.com/…
  workable        apply.workable.com
  teamtailor      *.teamtailor.com or pages with teamtailor-cdn.com assets
  dejobs          *.dejobs.org
  jobboardly      *.jobboardly.com or pages with assets.jobboardly.com

Returns None for unsupported or unrecognised platforms.
"""

import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests

# Fingerprints found in page source that identify an ATS even when the URL
# doesn't make it obvious (e.g. a custom careers subdomain).
_PAGE_FINGERPRINTS: list = [
    # (source_name, pattern_in_page_source)
    ("greenhouse", "boards-api.greenhouse.io"),
    ("greenhouse", "greenhouse.io/embed/job_board"),
    ("lever", "jobs.lever.co"),
    ("lever", "api.lever.co"),
    ("ashby", "ashbyhq.com"),
    ("workday", "myworkdayjobs.com"),
    ("smartrecruiters", "smartrecruiters.com"),
    ("workable", "apply.workable.com"),
    ("teamtailor", "teamtailor-cdn.com"),
    ("dejobs", "dejobs.org"),
    ("dejobs", "jobsyn.org"),
    ("jobboardly", "assets.jobboardly.com"),
]


def detect_ats(
    url: str,
    fetch_page: bool = True,
    timeout: int = 10,
) -> Optional[Tuple[str, Dict]]:
    """Detect the ATS platform from a careers URL.

    Args:
        url: A careers page URL or ATS-specific board URL.
        fetch_page: If True and URL pattern is ambiguous, fetch the page to
            look for ATS fingerprints in HTML/headers.
        timeout: HTTP request timeout in seconds.

    Returns:
        (source_name, config_dict) or None if unrecognised.
        config_dict is ready to insert as scraper_config.config.
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = parsed.path.strip("/")
    path_parts = [p for p in path.split("/") if p]

    # --- URL pattern rules (fast, no HTTP needed) ---

    # Greenhouse: boards.greenhouse.io/{token} or job-boards.greenhouse.io/{token}
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io"):
        if path_parts:
            return "greenhouse", {"token": path_parts[0]}

    # Lever: jobs.lever.co/{company} or lever.co/{company}
    if host in ("jobs.lever.co", "lever.co") and path_parts:
        return "lever", {"company": path_parts[0]}

    # Ashby: app.ashbyhq.com/careers/{subdomain} or jobs.ashbyhq.com/{subdomain}
    if host == "jobs.ashbyhq.com" and path_parts:
        return "ashby", {"subdomain": path_parts[0]}
    if (
        host == "app.ashbyhq.com"
        and len(path_parts) >= 2
        and path_parts[0] == "careers"
    ):
        return "ashby", {"subdomain": path_parts[1]}

    # Workday: {slug}.wd{N}.myworkdayjobs.com/{portal}
    workday_match = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host)
    if workday_match:
        slug = workday_match.group(1)
        wd = workday_match.group(2)
        portal = path_parts[0] if path_parts else ""
        if portal:
            return "workday", {
                "slug": slug,
                "wd": wd,
                "portal": portal,
                "max_jobs": 100,
            }

    # SmartRecruiters: jobs.smartrecruiters.com/{company_id}
    if host == "jobs.smartrecruiters.com" and path_parts:
        return "smartrecruiters", {
            "company_id": path_parts[0],
            "display_name": path_parts[0],
        }

    # Workable: apply.workable.com/{slug}
    if host == "apply.workable.com" and path_parts:
        return "workable", {"slug": path_parts[0], "name": path_parts[0]}

    # Teamtailor: {company}.teamtailor.com
    if host.endswith(".teamtailor.com"):
        return "teamtailor", {
            "career_url": f"{parsed.scheme}://{host}",
            "company": host.split(".")[0],
        }

    # DeJobs: {company}.dejobs.org
    if host.endswith(".dejobs.org"):
        return "dejobs", {"hostname": host, "name": host.split(".")[0], "max_jobs": 500}

    # Jobboardly: {subdomain}.jobboardly.com
    if host.endswith(".jobboardly.com"):
        subdomain = host[: -len(".jobboardly.com")]
        return "jobboardly", {"subdomain": subdomain}

    # --- Page fingerprint fallback (requires HTTP fetch) ---
    if not fetch_page:
        return None

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        page_text = resp.text
        # Also check CSP header — often reveals backend CDN/API URLs
        csp = resp.headers.get("content-security-policy", "")
        combined = page_text + csp
    except requests.RequestException:
        return None

    for source_name, fingerprint in _PAGE_FINGERPRINTS:
        if fingerprint in combined:
            config = _extract_config_from_page(source_name, url, page_text)
            if config is not None:
                return source_name, config

    # SmartRecruiters blind probe — handles custom-domain sites that call SR
    # internally without exposing it in HTML/JS (e.g. sixt.jobs → slug "sixt").
    # SR's public API accepts case-insensitive company slugs.
    sr_id = _probe_smartrecruiters(host, timeout=timeout)
    if sr_id:
        return "smartrecruiters", {
            "company_id": sr_id,
            "display_name": sr_id.capitalize(),
        }

    return None


def _probe_smartrecruiters(hostname: str, timeout: int = 8) -> Optional[str]:
    """Try the SmartRecruiters public API with slugs derived from the hostname.

    Returns the working company_id (lowercase slug) or None.
    Handles custom-domain careers sites that proxy SR without exposing it in HTML.
    """
    slug = re.sub(r"^(www|jobs|careers|work|talent|apply)\.", "", hostname)
    slug = re.sub(r"\.(com|io|org|net|co|uk|jobs|careers|app|us)$", "", slug)
    if "." in slug:
        slug = slug.split(".")[-1]
    slug = slug.lower()
    if not slug:
        return None

    for candidate in [slug, slug.capitalize()]:
        try:
            resp = requests.get(
                f"https://api.smartrecruiters.com/v1/companies/{candidate}/postings",
                params={"limit": 1},
                timeout=timeout,
            )
            if resp.status_code == 200 and resp.json().get("content"):
                return candidate
        except Exception:
            pass
    return None


def _extract_config_from_page(
    source_name: str, url: str, page_text: str
) -> Optional[Dict]:
    """Try to extract a config dict from page source after fingerprint match."""
    parsed = urlparse(url)
    host = parsed.hostname or ""

    if source_name == "greenhouse":
        # Look for board token in page source
        m = re.search(
            r"greenhouse\.io/embed/job_board\?for=([a-z0-9_-]+)", page_text, re.I
        )
        if m:
            return {"token": m.group(1)}
        m = re.search(r"boards\.greenhouse\.io/([a-z0-9_-]+)", page_text, re.I)
        if m:
            return {"token": m.group(1)}

    if source_name == "lever":
        m = re.search(r"jobs\.lever\.co/([a-z0-9_-]+)", page_text, re.I)
        if m:
            return {"company": m.group(1)}

    if source_name == "ashby":
        m = re.search(r"ashbyhq\.com/([a-z0-9_-]+)", page_text, re.I)
        if m:
            return {"subdomain": m.group(1)}

    if source_name == "workday":
        m = re.search(
            r'([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/[^/]*/([^/"]+)', page_text, re.I
        )
        if m:
            return {
                "slug": m.group(1),
                "wd": m.group(2),
                "portal": m.group(3),
                "max_jobs": 100,
            }

    if source_name == "smartrecruiters":
        m = re.search(r"smartrecruiters\.com/([A-Za-z0-9_-]+)", page_text)
        if m:
            cid = m.group(1)
            return {"company_id": cid, "display_name": cid}

    if source_name == "workable":
        m = re.search(r"apply\.workable\.com/([a-z0-9_-]+)", page_text, re.I)
        if m:
            return {"slug": m.group(1), "name": m.group(1)}

    if source_name == "teamtailor":
        # The career URL is the host itself if it ends in .teamtailor.com,
        # otherwise use the full URL as the career base
        if host.endswith(".teamtailor.com"):
            return {
                "career_url": f"{parsed.scheme}://{host}",
                "company": host.split(".")[0],
            }
        # Custom domain — use origin as career_url
        return {
            "career_url": f"{parsed.scheme}://{host}",
            "company": host.split(".")[0],
        }

    if source_name == "dejobs":
        if host.endswith(".dejobs.org"):
            return {"hostname": host, "name": host.split(".")[0], "max_jobs": 500}

    if source_name == "jobboardly":
        if host.endswith(".jobboardly.com"):
            subdomain = host[: -len(".jobboardly.com")]
            return {"subdomain": subdomain}

    return None


def validate_config(source_name: str, config: Dict, timeout: int = 10) -> bool:
    """Make a test API call to confirm the config is live and returns data.

    Returns True if the endpoint responds with at least one job, False otherwise.
    """
    try:
        if source_name == "greenhouse":
            token = config.get("token", "")
            url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
            r = requests.get(url, timeout=timeout)
            return r.status_code == 200 and bool(r.json().get("jobs"))

        if source_name == "lever":
            company = config.get("company", "")
            url = f"https://api.lever.co/v0/postings/{company}?mode=json&limit=1"
            r = requests.get(url, timeout=timeout)
            return (
                r.status_code == 200
                and isinstance(r.json(), list)
                and len(r.json()) > 0
            )

        if source_name == "ashby":
            subdomain = config.get("subdomain", "")
            url = f"https://api.ashbyhq.com/posting-api/job-board/{subdomain}"
            r = requests.get(url, timeout=timeout)
            return r.status_code == 200 and bool(r.json().get("jobPostings"))

        if source_name == "workday":
            slug = config.get("slug", "")
            wd = config.get("wd", "wd3")
            portal = config.get("portal", "")
            url = (
                f"https://{slug}.{wd}.myworkdayjobs.com"
                f"/wday/cxs/{slug}/{portal}/jobs"
            )
            r = requests.post(
                url,
                json={"limit": 1, "offset": 0, "searchText": "", "appliedFacets": {}},
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            return r.status_code == 200 and bool(r.json().get("jobPostings"))

        if source_name == "smartrecruiters":
            cid = config.get("company_id", "")
            url = f"https://api.smartrecruiters.com/v1/companies/{cid}/postings?limit=1"
            r = requests.get(url, timeout=timeout)
            return r.status_code == 200

        if source_name == "workable":
            slug = config.get("slug", "")
            url = f"https://apply.workable.com/api/v3/accounts/{slug}/jobs"
            r = requests.post(
                url,
                json={
                    "query": "",
                    "location": [],
                    "department": [],
                    "worktype": [],
                    "remote": [],
                },
                headers={"Content-Type": "application/json"},
                timeout=timeout,
            )
            return r.status_code == 200

        if source_name == "teamtailor":
            career_url = config.get("career_url", "")
            url = f"{career_url.rstrip('/')}/jobs.json"
            r = requests.get(url, timeout=timeout)
            return r.status_code == 200

        if source_name == "dejobs":
            hostname = config.get("hostname", "")
            url = "https://prod-search-api.jobsyn.org/api/v1/solr/search?q=&page=1"
            r = requests.get(url, headers={"x-origin": hostname}, timeout=timeout)
            return r.status_code == 200 and bool(r.json().get("jobs"))

        if source_name == "jobboardly":
            subdomain = config.get("subdomain", "")
            url = f"https://{subdomain}.jobboardly.com/jobs.json"
            r = requests.get(url, timeout=timeout)
            return r.status_code == 200 and isinstance(r.json(), list)

    except Exception:
        pass
    return False
