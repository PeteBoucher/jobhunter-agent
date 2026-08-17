"""Indra Group careers scraper.

Indra Group (https://careers.indragroup.com) uses SAP SuccessFactors
Recruiting Management with server-rendered HTML — there is no public JSON API.

Listing page: https://careers.indragroup.com/search?locale=es_ES
Structure:
  table
    tr.data-row                       ← one per job (25 per page)
      td.colTitle
        a.jobTitle-link               ← title text + href="/job/{slug}/{id}/"
        span.jobDate                  ← date e.g. "17 ago 2026"
      td.colLocation
        span.jobLocation              ← location e.g. "Madrid, ES"

Pagination: ?startrow=0 → 25 → 50 … (25 items per page, ~707 total at time of writing)
source_job_id: the numeric ID at the end of the job URL (stable across runs).
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.indragroup")

BASE_URL = "https://careers.indragroup.com"
SEARCH_URL = (
    "https://careers.indragroup.com/search"
    "?q=&sortColumn=referencedate&sortDirection=desc&locale=es_ES"
)
PAGE_SIZE = 25
MAX_JOBS = 500

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

_SPANISH_MONTHS = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
}


def _parse_date(text: str) -> Optional[datetime]:
    """Parse Spanish abbreviated date like '17 ago 2026'."""
    m = re.search(r"(\d{1,2})\s+([a-z]{3})\s+(\d{4})", text.lower().strip())
    if not m:
        return None
    month = _SPANISH_MONTHS.get(m.group(2))
    if not month:
        return None
    try:
        return datetime(int(m.group(3)), month, int(m.group(1)), tzinfo=timezone.utc)
    except ValueError:
        return None


class IndraGroupScraper(BaseScraper):
    """Scraper for Indra Group's SAP SuccessFactors careers portal."""

    def _get_source_name(self) -> str:
        return "indragroup"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        all_jobs: List[Dict[str, Any]] = []
        startrow = 0

        while len(all_jobs) < MAX_JOBS:
            url = f"{SEARCH_URL}&startrow={startrow}"
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Indra Group fetch error (startrow=%d): %s", startrow, e)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("tr.data-row")
            if not rows:
                break

            for row in rows:
                link = row.select_one("a.jobTitle-link")
                if not link:
                    continue

                href = link.get("href", "")
                # URL format: /job/{slug}/{numeric-id}/
                id_match = re.search(r"/(\d+)/?$", href)
                if not id_match:
                    continue

                location_tag = row.select_one("span.jobLocation")
                date_tag = row.select_one("span.jobDate")

                all_jobs.append(
                    {
                        "source_job_id": id_match.group(1),
                        "title": link.get_text(strip=True),
                        "apply_url": BASE_URL + href,
                        "location": location_tag.get_text(strip=True)
                        if location_tag
                        else None,
                        "posted_date": _parse_date(date_tag.get_text())
                        if date_tag
                        else None,
                    }
                )

            logger.info(
                "Fetched %d jobs (startrow=%d, page total=%d)",
                len(all_jobs),
                startrow,
                len(rows),
            )

            if len(rows) < PAGE_SIZE:
                break
            startrow += PAGE_SIZE

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        location = raw_job.get("location") or ""
        # Location format: "Madrid, ES" — country code is the last 2-char segment
        country = None
        if location:
            parts = [p.strip() for p in location.split(",")]
            if parts and len(parts[-1]) == 2:
                country = parts[-1].upper()

        return {
            "source_job_id": raw_job["source_job_id"],
            "title": raw_job.get("title"),
            "company": "Indra Group",
            "location": location,
            "country": country,
            "remote": None,
            "description": None,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": raw_job.get("apply_url"),
            "posted_date": raw_job.get("posted_date"),
            "salary_min": None,
            "salary_max": None,
            "company_industry": "Technology / Defense",
            "company_size": "Large (>10,000)",
            "source_type": "company_portal",
        }
