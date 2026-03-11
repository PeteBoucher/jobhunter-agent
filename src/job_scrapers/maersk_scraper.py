"""Maersk careers scraper via Workday's internal JSON API.

Workday does not publish an official public API, but their job search page
makes XHR calls to a predictable internal endpoint that returns JSON.

Search endpoint (POST):
  https://maersk.wd3.myworkdayjobs.com/wday/cxs/maersk/Maersk_Careers/jobs

Detail endpoint (GET, for full description):
  https://maersk.wd3.myworkdayjobs.com/wday/cxs/maersk/Maersk_Careers/job{externalPath}
"""

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.maersk")

WORKDAY_BASE = "https://maersk.wd3.myworkdayjobs.com"
PORTAL = "Maersk_Careers"
SEARCH_URL = f"{WORKDAY_BASE}/wday/cxs/maersk/{PORTAL}/jobs"
DETAIL_URL = f"{WORKDAY_BASE}/wday/cxs/maersk/{PORTAL}/job"
APPLY_BASE = f"{WORKDAY_BASE}/en-US/{PORTAL}"

# Workday returns pages of 20; we cap total fetched to avoid Lambda timeouts
PAGE_SIZE = 20
MAX_JOBS = 300

# Throttle between description fetches to be polite
DESCRIPTION_DELAY = 0.15  # seconds


class MaerskScraper(BaseScraper):
    """Scraper for Maersk careers (Workday-hosted).

    Fetches job listings from Maersk's Workday portal using the internal
    XHR API. For new jobs (not already in the DB), also fetches the full
    job description from the detail endpoint.
    """

    def __init__(self, session: Session):
        super().__init__(session)
        self._session_http = requests.Session()
        self._session_http.headers.update(
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
        return "maersk"

    def _fetch_all_listings(self) -> List[Dict[str, Any]]:
        """Fetch paginated job listing data from Workday search API."""
        listings: List[Dict[str, Any]] = []
        offset = 0

        while len(listings) < MAX_JOBS:
            payload = {
                "limit": PAGE_SIZE,
                "offset": offset,
                "searchText": "",
                "locations": [],
                "appliedFacets": {},
            }
            try:
                resp = self._session_http.post(SEARCH_URL, json=payload, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning(f"Maersk search API error at offset {offset}: {e}")
                break

            data = resp.json()
            page = data.get("jobPostings", [])
            if not page:
                break

            listings.extend(page)
            total = data.get("total", 0)
            offset += PAGE_SIZE

            if offset >= total:
                break

        logger.info(f"Fetched {len(listings)} Maersk job listings")
        return listings

    def _fetch_description(self, external_path: str) -> Optional[str]:
        """Fetch full job description HTML from the Workday detail endpoint."""
        # external_path starts with '/' e.g. '/job/London/Engineer_R12345'
        # strip leading '/job' since it's already in DETAIL_URL pattern:
        # DETAIL_URL + external_path => .../job/job/... — we want just the slug
        path = external_path.lstrip("/")  # e.g. 'job/London/Engineer_R12345'
        url = f"{WORKDAY_BASE}/wday/cxs/maersk/{PORTAL}/{path}"
        try:
            resp = self._session_http.get(url, timeout=15)
            resp.raise_for_status()
            info = resp.json().get("jobPostingInfo", {})
            return info.get("jobDescription") or info.get("jobDescription")
        except Exception as e:
            logger.debug(f"Could not fetch description for {path}: {e}")
            return None

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch listings, then hydrate new jobs with full descriptions."""
        listings = self._fetch_all_listings()
        if not listings:
            return []

        # Check which job IDs are already in the DB (one query)
        existing_ids: set = self._load_existing_ids()

        result: List[Dict[str, Any]] = []
        new_count = 0

        for listing in listings:
            job_id = listing.get("jobReqId", "")
            listing["_description_html"] = None

            if job_id and job_id not in existing_ids:
                external_path = listing.get("externalPath", "")
                if external_path:
                    listing["_description_html"] = self._fetch_description(
                        external_path
                    )
                    time.sleep(DESCRIPTION_DELAY)
                new_count += 1

            result.append(listing)

        logger.info(
            f"Maersk: {len(listings)} total, {new_count} new (descriptions fetched)"
        )
        return result

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Workday job posting into standardised format."""
        job_id = raw_job.get("jobReqId", "")
        title = raw_job.get("title", "")
        external_path = raw_job.get("externalPath", "")
        locations_text = raw_job.get("locationsText", "")
        bullet_fields = raw_job.get("bulletFields", [])
        posted_on = raw_job.get("postedOn", "")

        # Department is usually the first bullet field
        department = bullet_fields[0] if bullet_fields else None

        # Remote detection
        remote = _parse_remote(locations_text)

        # Apply URL
        apply_url = f"{APPLY_BASE}{external_path}" if external_path else APPLY_BASE

        # Description
        html = raw_job.get("_description_html") or ""
        description = _strip_html(html)[:5000] if html else None

        # Posted date
        posted_date = _parse_posted_on(posted_on)

        return {
            "source_job_id": job_id,
            "title": title,
            "company": "Maersk",
            "department": department,
            "location": locations_text or None,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "company_industry": "Logistics / Shipping",
            "company_size": "Enterprise (100k+)",
            "source_type": "company_portal",
        }


# ── Helpers ──────────────────────────────────────────────────────────────────


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
        days = int(match.group(1))
        return now - timedelta(days=days)
    return now
