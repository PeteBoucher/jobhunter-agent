"""Jobboardly multi-tenant job board scraper.

Jobboardly (https://jobboardly.com) is a white-label job board platform.
Each tenant gets their own subdomain: https://{subdomain}.jobboardly.com/

API: GET /jobs.json — returns all live jobs for the board in a single response
(no pagination). Jobs typically come from multiple companies; application_link
points directly to the company's own ATS.

Config shape (scraper_config table):
    {"subdomain": "iglubit-1", "display_name": "Iglubit Tech Jobs"}

Hardcoded defaults below; add more boards via:
    job-agent scraper add https://{subdomain}.jobboardly.com
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.jobboardly")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

DEFAULT_BOARDS = [
    {"subdomain": "iglubit-1", "display_name": "Iglubit Tech Jobs"},
]


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or None


def _parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class JobboardlyScraper(BaseScraper):
    """Scraper for Jobboardly-hosted job boards."""

    def _get_source_name(self) -> str:
        return "jobboardly"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db_boards = [c for c in self._load_db_config() if "subdomain" in c]
        boards = db_boards if db_boards else DEFAULT_BOARDS

        all_jobs: List[Dict[str, Any]] = []
        for board in boards:
            subdomain = board["subdomain"]
            display = board.get("display_name", subdomain)
            url = f"https://{subdomain}.jobboardly.com/jobs.json"
            try:
                resp = requests.get(url, headers=_HEADERS, timeout=20)
                resp.raise_for_status()
                jobs = resp.json()
                if not isinstance(jobs, list):
                    logger.warning(
                        "Unexpected Jobboardly response type from %s: %s",
                        subdomain,
                        type(jobs).__name__,
                    )
                    continue
                for job in jobs:
                    job["_board_subdomain"] = subdomain
                all_jobs.extend(jobs)
                logger.info(
                    "Fetched %d jobs from Jobboardly board %s", len(jobs), display
                )
            except requests.RequestException as e:
                logger.warning("Jobboardly fetch error (%s): %s", subdomain, e)

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        subdomain = raw_job.get("_board_subdomain", "unknown")

        # Stable ID: slug from links.self (/jobs/{slug})
        self_url = (raw_job.get("links") or {}).get("self", "")
        slug = self_url.rstrip("/").split("/")[-1] if self_url else None
        source_job_id = f"{subdomain}:{slug}" if slug else None

        # `location` is "remote" or "onsite" — a work-arrangement flag, not a city.
        # The actual geographic location is in company.location ("Sevilla, Spain").
        arrangement = (raw_job.get("location") or "").strip().lower()
        remote = arrangement == "remote"

        company_info = raw_job.get("company") or {}
        company = company_info.get("name") if isinstance(company_info, dict) else None
        geo_location = (
            company_info.get("location") if isinstance(company_info, dict) else None
        )

        # Country: prefer location_limits (ISO2 list), fall back to base class inference
        country: Optional[str] = None
        limits = raw_job.get("location_limits") or []
        if limits and isinstance(limits, list):
            country = str(limits[0]).upper()

        description_block = raw_job.get("description") or {}
        description_html = (
            description_block.get("html")
            if isinstance(description_block, dict)
            else None
        )

        salary = raw_job.get("salary") or {}
        salary_min = salary.get("minimum") if isinstance(salary, dict) else None
        salary_max = salary.get("maximum") if isinstance(salary, dict) else None

        # application_link is the canonical apply URL at the company's own ATS
        apply_url = raw_job.get("application_link") or self_url or None

        return {
            "source_job_id": source_job_id,
            "title": raw_job.get("title"),
            "company": company,
            "location": geo_location,
            "country": country,
            "remote": remote,
            "description": _strip_html(description_html),
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": _parse_date(raw_job.get("published_at")),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "company_industry": None,
            "company_size": None,
            "source_type": "job_board",
        }
