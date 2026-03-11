"""Generic Workday job board scraper.

Workday does not publish an official public API, but their job search page
makes XHR calls to a predictable internal endpoint that returns JSON.

Search endpoint (POST):
  https://{slug}.wd{N}.myworkdayjobs.com/wday/cxs/{slug}/{portal}/jobs

Detail endpoint (GET, for full description):
  https://{slug}.wd{N}.myworkdayjobs.com/wday/cxs/{slug}/{portal}{externalPath}

To add a new company: verify the endpoint manually, then add a WorkdayPortal
entry to WORKDAY_PORTALS below.

Confirmed working portals (as of 2025-03):
  Maersk        — maersk.wd3          / Maersk_Careers                   (~500 jobs)
  Airbus        — ag.wd3              / Airbus                           (~2000 jobs)
  Shell         — shell.wd3           / shellcareers                      (~180 jobs)
  AstraZeneca   — astrazeneca.wd3     / Careers                          (~1100 jobs)
  BP            — bpinternational.wd3 / bpCareers                         (~400 jobs)
  Unilever      — unilever.wd3        / Unilever_Experienced_Professionals (~420 jobs)
  GSK           — gsk.wd5             / GSKCareers                       (~1600 jobs)
  Netflix       — netflix.wd1         / Netflix                           (~790 jobs)
  Adobe         — adobe.wd5           / external_experienced             (~1100 jobs)
  Accenture     — accenture.wd103     / AccentureCareers                  (~2000 jobs)
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.workday")

# Throttle between per-job description fetches to be polite
DESCRIPTION_DELAY = 0.1  # seconds

# Workday returns pages of 20; cap total per portal to avoid Lambda timeouts.
# Lower than original 300 because we now have 10 portals — first-run description
# fetches are capped at MAX_JOBS_PER_PORTAL × DESCRIPTION_DELAY seconds each.
PAGE_SIZE = 20
MAX_JOBS_PER_PORTAL = 100


@dataclass
class WorkdayPortal:
    """Configuration for a single Workday-hosted careers portal."""

    slug: str  # subdomain slug, e.g. "maersk"
    portal: str  # portal path segment, e.g. "Maersk_Careers"
    company: str  # display name, e.g. "Maersk"
    wd: str = "wd3"  # Workday instance number (wd1, wd3, wd5 …)
    industry: str = "Technology"
    size: str = "Enterprise"

    @property
    def base_url(self) -> str:
        return f"https://{self.slug}.{self.wd}.myworkdayjobs.com"

    @property
    def search_url(self) -> str:
        return f"{self.base_url}/wday/cxs/{self.slug}/{self.portal}/jobs"

    @property
    def apply_base(self) -> str:
        return f"{self.base_url}/en-US/{self.portal}"


# ── Confirmed working portals ─────────────────────────────────────────────────

WORKDAY_PORTALS: List[WorkdayPortal] = [
    WorkdayPortal(
        slug="maersk",
        portal="Maersk_Careers",
        company="Maersk",
        industry="Logistics / Shipping",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="ag",
        portal="Airbus",
        company="Airbus",
        industry="Aerospace / Defence",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="shell",
        portal="shellcareers",
        company="Shell",
        industry="Energy",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="astrazeneca",
        portal="Careers",
        company="AstraZeneca",
        industry="Pharmaceutical",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="bpinternational",
        portal="bpCareers",
        company="BP",
        industry="Energy",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="unilever",
        portal="Unilever_Experienced_Professionals",
        company="Unilever",
        industry="Consumer Goods",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="gsk",
        portal="GSKCareers",
        company="GSK",
        wd="wd5",
        industry="Pharmaceutical",
        size="Enterprise (100k+)",
    ),
    WorkdayPortal(
        slug="netflix",
        portal="Netflix",
        company="Netflix",
        wd="wd1",
        industry="Technology / Media",
        size="Large (10k+)",
    ),
    WorkdayPortal(
        slug="adobe",
        portal="external_experienced",
        company="Adobe",
        wd="wd5",
        industry="Technology",
        size="Large (10k+)",
    ),
    WorkdayPortal(
        slug="accenture",
        portal="AccentureCareers",
        company="Accenture",
        wd="wd103",
        industry="Consulting / Technology",
        size="Enterprise (100k+)",
    ),
]


# ── Scraper ───────────────────────────────────────────────────────────────────


class WorkdayScraper(BaseScraper):
    """Scraper for Workday-hosted careers portals.

    Fetches job listings from multiple companies using Workday's internal
    XHR API. For new jobs (not already in the DB), also fetches the full
    job description from the detail endpoint.

    source_job_id format: "{slug}:{jobReqId}" to avoid cross-company collisions.
    """

    def __init__(self, session: Session, portals: Optional[List[WorkdayPortal]] = None):
        super().__init__(session)
        self.portals = portals or WORKDAY_PORTALS
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "workday"

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _fetch_portal_listings(self, portal: WorkdayPortal) -> List[Dict[str, Any]]:
        """Paginate through all job listings for a single portal."""
        listings: List[Dict[str, Any]] = []
        offset = 0

        while len(listings) < MAX_JOBS_PER_PORTAL:
            try:
                resp = self._http.post(
                    portal.search_url,
                    json={
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "searchText": "",
                        "locations": [],
                        "appliedFacets": {},
                    },
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning(
                    "Workday search error [%s] at offset %d: %s",
                    portal.company,
                    offset,
                    e,
                )
                break

            data = resp.json()
            page = data.get("jobPostings", [])
            if not page:
                break

            # Tag each listing with portal metadata for later use
            for job in page:
                job["_portal"] = portal

            listings.extend(page)
            total = data.get("total", 0)
            offset += PAGE_SIZE
            if offset >= total:
                break

        logger.info("Fetched %d listings from %s", len(listings), portal.company)
        return listings

    def _fetch_description(
        self, portal: WorkdayPortal, external_path: str
    ) -> Optional[str]:
        """Fetch full job description HTML from the Workday detail endpoint."""
        # external_path e.g. '/job/Copenhagen/Engineer_R12345'
        path = external_path.lstrip("/")
        url = f"{portal.base_url}/wday/cxs/{portal.slug}/{portal.portal}/{path}"
        try:
            resp = self._http.get(url, timeout=15)
            resp.raise_for_status()
            return resp.json().get("jobPostingInfo", {}).get("jobDescription")
        except Exception as e:
            logger.debug(
                "Could not fetch description for %s %s: %s",
                portal.company,
                path,
                e,
            )
            return None

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch listings from all portals; hydrate new jobs with descriptions."""
        existing_ids: set = self._load_existing_ids()
        all_raw: List[Dict[str, Any]] = []

        for portal in self.portals:
            try:
                listings = self._fetch_portal_listings(portal)
            except Exception as e:
                logger.warning("Failed to fetch listings for %s: %s", portal.company, e)
                continue

            new_count = 0
            for listing in listings:
                job_req_id = listing.get("jobReqId", "")
                source_job_id = f"{portal.slug}:{job_req_id}"
                listing["_source_job_id"] = source_job_id
                listing["_description_html"] = None

                if source_job_id not in existing_ids:
                    external_path = listing.get("externalPath", "")
                    if external_path:
                        listing["_description_html"] = self._fetch_description(
                            portal, external_path
                        )
                        time.sleep(DESCRIPTION_DELAY)
                    new_count += 1

                all_raw.append(listing)

            logger.info(
                "%s: %d total, %d new", portal.company, len(listings), new_count
            )

        return all_raw

    # ── Parse ─────────────────────────────────────────────────────────────────

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Workday job posting into standardised format."""
        portal: WorkdayPortal = raw_job["_portal"]
        external_path = raw_job.get("externalPath", "")
        locations_text = raw_job.get("locationsText", "")
        bullet_fields = raw_job.get("bulletFields", [])

        department = bullet_fields[0] if bullet_fields else None
        remote = _parse_remote(locations_text)
        apply_url = (
            f"{portal.apply_base}{external_path}"
            if external_path
            else portal.apply_base
        )

        html = raw_job.get("_description_html") or ""
        description = _strip_html(html)[:5000] if html else None

        return {
            "source_job_id": raw_job.get("_source_job_id", ""),
            "title": raw_job.get("title", ""),
            "company": portal.company,
            "department": department,
            "location": locations_text or None,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": _parse_posted_on(raw_job.get("postedOn", "")),
            "company_industry": portal.industry,
            "company_size": portal.size,
            "source_type": "company_portal",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_remote(locations_text: str) -> Optional[str]:
    loc = locations_text.lower()
    if "hybrid" in loc:
        return "hybrid"
    if "remote" in loc:
        return "remote"
    return None


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _parse_posted_on(posted_on: str) -> datetime:
    """Convert Workday 'Posted X Days Ago' string to a datetime."""
    now = datetime.utcnow()
    if not posted_on:
        return now
    text = posted_on.lower()
    if "today" in text:
        return now
    match = re.search(r"(\d+)\+?\s+day", text)
    if match:
        return now - timedelta(days=int(match.group(1)))
    return now
