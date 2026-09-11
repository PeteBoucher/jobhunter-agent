"""50skills job board scraper.

50skills is an ATS whose hosted career sites live at
jobs.50skills.com/{company}[/{lang}] — a bare React SPA (a ~2KB HTML shell,
`<div id="root">`) with zero server-rendered content, so neither a plain
fetch nor the AI generator's static/HTML-sample probing ever finds anything.
There's also no ATS fingerprint anywhere in the shell HTML (no CDN hostname,
no recognizable script src pattern) — even the AI generator's headless
Chromium capture found nothing here on a first pass.

The real API was found by downloading the SPA's JS bundle
(https://ui-jobs.50skills.app/static/index-*.js) and grepping for API host
literals: the bundle builds requests from a handful of minified base-URL
constants, e.g. ``${oU}/public/${slug}/jobs.json`` where
``oU = "https://static-jobs-api.50skills.app"``. Confirmed live against
Carbfix (jobs.50skills.com/carbfix).

API endpoints (unauthenticated JSON, no pagination seen):
  GET https://static-jobs-api.50skills.app/public/{slug}/jobs.json
      -> [ {id, url, companyFullName, jobType, workType, status, deadline,
            languages: [{language, title, shortDescription, description
            (HTML), location (free-text, inconsistent — see below)}],
            category, department, location, labels, visibility}, ... ]
      `location`/`department` are numeric ids, not names.

  GET https://static-jobs-api.50skills.app/company/{slug}.json
      -> {companyName, defaultLanguage, languages, departments, locations}
      `locations`/`departments` are [{id, translations: [{language, title}]}]
      — the lookup table that resolves the numeric ids on each job. Fetched
      once per company per scrape run, not per job.

No posted-date field exists anywhere in either endpoint (checked both the
list and the per-job detail endpoint) — falls back to `datetime.utcnow()`
like teamtailor_scraper.py does for the same reason.

To add a new company: find their 50skills career URL
(jobs.50skills.com/{slug}), verify both endpoints above resolve for that
slug, then add a FiftySkillsBoard entry to DEFAULT_BOARDS below.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.fiftyskills")

_API_BASE = "https://static-jobs-api.50skills.app"


@dataclass
class FiftySkillsBoard:
    """Configuration for a single 50skills-hosted career site."""

    company: str  # display name, e.g. "Carbfix"
    slug: str  # 50skills company slug, e.g. "carbfix" (from the URL path)


DEFAULT_BOARDS: List[FiftySkillsBoard] = [
    FiftySkillsBoard(company="Carbfix", slug="carbfix"),
]


class FiftySkillsScraper(BaseScraper):
    """Scraper for 50skills-hosted career sites.

    Two requests per company: the job list, and the company/locations
    lookup used to resolve each job's numeric location/department id to a
    translated name. No per-job detail fetch needed — the detail endpoint
    (``/public/{slug}/jobs/{id}.json``) returns nothing the list doesn't
    already have.
    """

    def __init__(
        self, session: Session, boards: Optional[List[FiftySkillsBoard]] = None
    ):
        super().__init__(session)
        self.boards = boards or DEFAULT_BOARDS
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "fiftyskills"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db_boards = [
            FiftySkillsBoard(
                company=c.get("company", c.get("slug", "")),
                slug=c["slug"],
            )
            for c in self._load_db_config()
            if "slug" in c
        ]
        boards = self.boards + db_boards
        all_raw: List[Dict[str, Any]] = []

        for board in boards:
            try:
                resp = self._http.get(
                    f"{_API_BASE}/public/{board.slug}/jobs.json", timeout=15
                )
                resp.raise_for_status()
                jobs = resp.json()
            except requests.RequestException as e:
                logger.warning("50skills fetch error [%s]: %s", board.company, e)
                continue
            except ValueError as e:
                logger.warning("50skills invalid JSON [%s]: %s", board.company, e)
                continue

            lookup = _fetch_lookup(self._http, board.slug)

            for job in jobs:
                job["_board"] = board
                job["_lookup"] = lookup
            all_raw.extend(jobs)
            logger.info("Fetched %d jobs from %s", len(jobs), board.company)

        return all_raw

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        board: FiftySkillsBoard = raw_job["_board"]
        lookup: Dict[str, Any] = raw_job["_lookup"]

        job_id = str(raw_job.get("id") or "")
        lang = _pick_language(raw_job.get("languages") or [])

        title = (lang or {}).get("title") or ""
        description_html = (lang or {}).get("description") or ""
        description = _strip_html(description_html)[:5000] if description_html else None

        location = _resolve_label(raw_job.get("location"), lookup.get("locations"))
        department = _resolve_label(
            raw_job.get("department"), lookup.get("departments")
        )

        remote = _parse_remote(location, description)

        apply_url = raw_job.get("url") or f"https://jobs.50skills.com/{board.slug}"

        return {
            "source_job_id": f"{board.slug}:{job_id}",
            "title": title,
            "company": board.company,
            "department": department,
            "location": location,
            "remote": remote,
            "country": None,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": datetime.utcnow(),
            "source_type": "company_portal",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fetch_lookup(http: requests.Session, slug: str) -> Dict[str, Any]:
    """Fetch the company config once per board — its `locations`/`departments`
    arrays are the id->translated-name lookup tables for job.location/
    job.department. Returns {} on any failure so parsing degrades to raw ids
    rather than raising."""
    try:
        resp = http.get(f"{_API_BASE}/company/{slug}.json", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return {
            "locations": data.get("locations") or [],
            "departments": data.get("departments") or [],
        }
    except (requests.RequestException, ValueError) as e:
        logger.warning("50skills company lookup failed [%s]: %s", slug, e)
        return {}


def _resolve_label(
    item_id: Any, table: Optional[List[Dict[str, Any]]]
) -> Optional[str]:
    """Resolve a numeric location/department id to its English translation
    (falling back to the first available translation) via the company's
    lookup table. Returns None if the id is unset or unresolvable."""
    if item_id is None or not table:
        return None
    for entry in table:
        if entry.get("id") == item_id:
            translations = entry.get("translations") or []
            for t in translations:
                if t.get("language") == "en" and t.get("title"):
                    return t["title"]
            if translations:
                return translations[0].get("title")
    return None


def _pick_language(
    languages: List[Dict[str, Any]], preferred: str = "en"
) -> Optional[Dict[str, Any]]:
    """Pick the preferred-language entry from a job's `languages` list,
    falling back to the first entry if the preferred language isn't posted."""
    for entry in languages:
        if entry.get("language") == preferred:
            return entry
    return languages[0] if languages else None


def _parse_remote(location: Optional[str], description: Optional[str]) -> Optional[str]:
    """50skills has no explicit remote/hybrid/onsite field. Infer from the
    resolved location label (seen live: a location translated to "Anywhere"
    is how Carbfix marks a fully remote role) and fall back to a keyword
    scan of the description, same approach as teamtailor_scraper.py."""
    loc = (location or "").lower()
    if "anywhere" in loc or "remote" in loc:
        return "remote"
    if "hybrid" in loc:
        return "hybrid"
    desc = (description or "").lower()[:500]
    if "hybrid" in desc:
        return "hybrid"
    if "remote" in desc:
        return "remote"
    return None


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean
