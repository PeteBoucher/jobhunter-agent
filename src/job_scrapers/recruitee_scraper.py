"""Recruitee job board scraper.

Recruitee is an ATS whose "Career Site Builder" product renders job
listings directly into a company's own page — either a {company}.recruitee.com
subdomain or a custom domain (e.g. meet.zoi.tech). Either way it exposes a
public JSON API, unauthenticated, at /api/offers/.

Discovered via meet.zoi.tech: its homepage lists 11 open positions with
/o/{slug} links and mentions "recruitee" ~90 times in the page source
(recruiteecdn.com asset host), but the AI scraper generator couldn't find
a live endpoint via static probing or headless network capture — the
homepage IS the job listing (no separate XHR call fires; it's server-side
rendered), so the generator's HTML-sample fallback should have found it,
but the class-name heuristics didn't match Recruitee's markup. The actual
API only turned up by testing the well-known Recruitee endpoint pattern
directly against the custom domain.

API endpoint:
  GET https://{career_site}/api/offers/
  Returns {"offers": [...]}, no pagination — all published offers at once.

To add a new company: find their Recruitee career URL (look for
'recruiteecdn.com' or "recruitee" in page source), verify the
/api/offers/ endpoint works, then add a RecruiteeBoard entry to
DEFAULT_BOARDS below.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.recruitee")


@dataclass
class RecruiteeBoard:
    """Configuration for a single Recruitee-hosted career site."""

    company: str  # display name, e.g. "Zoi"
    career_url: str  # base URL of the Recruitee career site


DEFAULT_BOARDS: List[RecruiteeBoard] = [
    RecruiteeBoard(
        company="Zoi",
        career_url="https://meet.zoi.tech",
    ),
]


class RecruiteeScraper(BaseScraper):
    """Scraper for Recruitee-hosted career sites.

    Uses the public /api/offers/ JSON endpoint, which returns full offer
    detail (description, location, remote/hybrid flags, salary) in one
    unauthenticated request — no per-job detail fetch needed.
    """

    def __init__(self, session: Session, boards: Optional[List[RecruiteeBoard]] = None):
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
        return "recruitee"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db_boards = [
            RecruiteeBoard(
                company=c.get("company", c.get("career_url", "")),
                career_url=c["career_url"],
            )
            for c in self._load_db_config()
            if "career_url" in c
        ]
        boards = self.boards + db_boards
        all_raw: List[Dict[str, Any]] = []

        for board in boards:
            url = f"{board.career_url.rstrip('/')}/api/offers/"
            try:
                resp = self._http.get(url, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Recruitee fetch error [%s]: %s", board.company, e)
                continue

            data = resp.json()
            offers = data.get("offers", [])
            for offer in offers:
                offer["_board"] = board
            all_raw.extend(offers)
            logger.info("Fetched %d jobs from %s", len(offers), board.company)

        return all_raw

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        board: RecruiteeBoard = raw_job["_board"]

        job_id = str(raw_job.get("id") or raw_job.get("slug") or "")
        title = raw_job.get("title") or ""

        description_html = raw_job.get("description") or ""
        description = _strip_html(description_html)[:5000] if description_html else None

        requirements_html = raw_job.get("requirements") or ""
        requirements = (
            _strip_html(requirements_html)[:2000] if requirements_html else None
        )

        location = raw_job.get("city") or raw_job.get("location")
        country_code = (raw_job.get("country_code") or "").lower() or None

        remote = _parse_remote(raw_job)

        salary = raw_job.get("salary") or {}
        salary_min = salary.get("min")
        salary_max = salary.get("max")

        posted_date = _parse_date(raw_job.get("published_at"))

        apply_url = raw_job.get("careers_url") or board.career_url

        return {
            "source_job_id": f"{_slug(board.company)}:{job_id}",
            "title": title,
            "company": board.company,
            "department": raw_job.get("department"),
            "location": location,
            "remote": remote,
            "country": country_code,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "source_type": "company_portal",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_remote(offer: Dict[str, Any]) -> Optional[str]:
    """Map Recruitee's remote/hybrid/on_site booleans to the canonical enum."""
    if offer.get("remote"):
        return "remote"
    if offer.get("hybrid"):
        return "hybrid"
    if offer.get("on_site"):
        return "onsite"
    return None


def _parse_date(date_str: Optional[str]) -> datetime:
    """Parse Recruitee's "YYYY-MM-DD HH:MM:SS UTC" timestamp format."""
    if not date_str:
        return datetime.utcnow()
    try:
        return datetime.strptime(date_str.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return datetime.utcnow()


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
