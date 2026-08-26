"""bunq careers scraper.

bunq's careers site (https://careers.bunq.com/positions) is a Framer-built
page. It is NOT client-rendered — the listing and each job's detail page
are both server-rendered with real content in the static HTML — but the
AI-generated first draft of this scraper used a loose regex over any
h2/h3/<a> tag, which matched real job titles AND nav/UI chrome ("Discover
bunq", "Filter by country", "Offices", ...) as if they were jobs, and never
found each job's real per-job link (every "job" pointed at the generic
listing URL). The schema validator didn't catch this because the output
was still structurally well-formed — the bug was semantic, not structural.

The real per-job link IS present in static HTML — it just wraps the job
card as a parent, not a child (`<a class="framer-1int89f">` around a `div`
with the title/department), which a naive `container.find("a")` (searching
descendants) misses.

Structure:
  Listing page (/positions): each real job is
    `<a class="framer-1int89f" href="./positions/{slug}">` containing an
    `<h3>` title and a `data-framer-name="Department"` field. 10 real jobs
    on the page at time of writing — filtering by this specific anchor
    class excludes all the nav/filter/footer noise the naive regex caught.

  Detail page (/positions/{slug}): work-mode ("Hybrid"/"Remote"/"On-site")
    and city are the two children of
    `header[data-framer-name="Header"] div[data-framer-name="Details"]` —
    confirmed stable across repeated fetches of the same URL.

    The full job description is a `div[data-framer-name="Content wrapper"]`
    too, but that name is reused for short marketing teasers ("Discover
    bunq...", "Our culture...", ~130-140 chars) elsewhere on the same page,
    AND — separately — the real long-form description (~4000 chars,
    confirmed present at least once) did not reappear in 5/5 follow-up
    fetches of the identical URL with plain requests.get(). Something about
    this page's server-side rendering doesn't reliably flush the full
    content on every request (framework streaming/Suspense behavior is the
    likely cause, not verified further). Rather than risk silently storing
    the wrong 140-char teaser as if it were the job description, only a
    match over 500 chars is accepted; otherwise description is left None.
    Title/department/location/remote/apply_url are unaffected and reliable.

Country is derived from a small hardcoded city->country map, not left for
the base class to infer — bunq posts roles across NL/BE/US/BG/TR (the
original draft hardcoded "nl" for every job, which is wrong for most of
them), and BaseScraper._infer_country() only detects country names or a
US-state enumeration inside free text; it doesn't geocode city names like
"Amsterdam". Multi-city locations (e.g. "Sofia/Istanbul", shown as-is when
a role is open in more than one office) are left as country=None — there's
no single correct answer for those.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.bunq")

# No trailing slash: urljoin(CAREERS_URL, "./positions/x") only resolves to
# the correct .../positions/x (not .../positions/positions/x) without one.
CAREERS_URL = "https://careers.bunq.com/positions"

_JOB_ANCHOR_CLASS = "framer-1int89f"


class BunqScraper(BaseScraper):
    """Scraper for bunq's careers site."""

    def __init__(self, session: Session):
        super().__init__(session)
        self._http = requests.Session()
        self._http.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "bunq"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        try:
            resp = self._http.get(CAREERS_URL, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("bunq fetch error: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs: List[Dict[str, Any]] = []

        for anchor in soup.find_all("a", class_=_JOB_ANCHOR_CLASS, href=True):
            href = anchor["href"]
            title_el = anchor.find("h3")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            department_el = anchor.find(attrs={"data-framer-name": "Department"})
            department = department_el.get_text(strip=True) if department_el else None

            jobs.append(
                {
                    "title": title,
                    "detail_url": urljoin(CAREERS_URL, href),
                    "department": department,
                }
            )

        logger.info("Fetched %d jobs from bunq", len(jobs))
        return jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        detail_url = raw_job["detail_url"]
        slug = detail_url.rstrip("/").split("/")[-1]

        location, remote, description = self._fetch_job_detail(detail_url)

        return {
            "source_job_id": slug,
            "title": raw_job["title"],
            "company": "bunq",
            "department": raw_job.get("department"),
            "location": location,
            "remote": remote,
            "country": _country_from_location(location),
            "description": description,
            "requirements": None,
            "apply_url": detail_url,
            "posted_date": datetime.utcnow(),
            "source_type": "company_portal",
        }

    def _fetch_job_detail(
        self, detail_url: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Returns (location, remote, description) from a job detail page."""
        try:
            resp = self._http.get(detail_url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to fetch job detail %s: %s", detail_url, e)
            return None, None, None

        try:
            soup = BeautifulSoup(resp.text, "html.parser")

            location: Optional[str] = None
            remote: Optional[str] = None
            header = soup.find("header", attrs={"data-framer-name": "Header"})
            if header:
                details = header.find("div", attrs={"data-framer-name": "Details"})
                if details:
                    children = details.find_all(recursive=False)
                    if len(children) >= 2:
                        remote = _parse_work_mode(children[0].get_text(strip=True))
                        location = children[1].get_text(strip=True) or None

            # The same data-framer-name is reused for ~140-char marketing
            # teasers elsewhere on the page; only accept a match long enough
            # to plausibly be the real job description (see module docstring
            # — the real one doesn't reliably render on every fetch at all).
            description = None
            wrappers = soup.find_all(
                "div", attrs={"data-framer-name": "Content wrapper"}
            )
            if wrappers:
                longest = max(wrappers, key=lambda w: len(w.get_text(strip=True)))
                text = longest.get_text(separator=" ", strip=True)
                if len(text) > 500:
                    description = text[:5000]

            return location, remote, description
        except Exception as e:
            logger.warning("Error parsing job detail %s: %s", detail_url, e)
            return None, None, None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_work_mode(text: str) -> Optional[str]:
    normalized = re.sub(r"[\s-]+", "", text.lower())
    if "hybrid" in normalized:
        return "hybrid"
    if "remote" in normalized:
        return "remote"
    if "onsite" in normalized:
        return "onsite"
    return None


# bunq's known office cities. Not a general geocoder — just the specific
# set this scraper has actually observed in the "Location" field.
_CITY_COUNTRY = {
    "amsterdam": "nl",
    "new york": "us",
    "brussels": "be",
    "sofia": "bg",
    "istanbul": "tr",
}


def _country_from_location(location: Optional[str]) -> Optional[str]:
    """Map a single known city to its country. Multi-city strings (e.g.
    "Sofia/Istanbul", used when a role is open in more than one office)
    have no single correct answer, so they're left unmapped (None)."""
    if not location or "/" in location:
        return None
    return _CITY_COUNTRY.get(location.strip().lower())
