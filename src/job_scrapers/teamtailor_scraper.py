"""Teamtailor job board scraper.

Teamtailor is an ATS used by many European tech companies. Each company
hosts its own branded career site, which exposes a public JSON Feed at
/jobs.json (RFC 9116 compliant) without authentication.

JSON Feed endpoint:
  GET https://{career_site}/jobs.json

Each item has a '_jobposting' field containing a Schema.org JobPosting
dict with location (city + country), date, and full HTML description.

To add a new company: find their Teamtailor career URL (look for
'teamtailor-cdn.com' in page source), verify the /jobs.json endpoint
works, then add a TeamtailorBoard entry to DEFAULT_BOARDS below.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.teamtailor")


@dataclass
class TeamtailorBoard:
    """Configuration for a single Teamtailor-hosted career site."""

    company: str  # display name, e.g. "The Workshop"
    career_url: str  # base URL of the Teamtailor career site


DEFAULT_BOARDS: List[TeamtailorBoard] = [
    TeamtailorBoard(
        company="The Workshop",
        career_url="https://careers.theworkshop.com",
    ),
    TeamtailorBoard(
        company="Oatly",
        career_url="https://oatly.teamtailor.com",
    ),
    TeamtailorBoard(
        company="Hedvig",
        career_url="https://hedvig.teamtailor.com",
    ),
    TeamtailorBoard(
        company="Storytel",
        career_url="https://storytel.teamtailor.com",
    ),
]


class TeamtailorScraper(BaseScraper):
    """Scraper for Teamtailor-hosted career sites.

    Uses the public JSON Feed at /jobs.json which contains Schema.org
    JobPosting data including location, description, and posting date.
    """

    def __init__(
        self, session: Session, boards: Optional[List[TeamtailorBoard]] = None
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
        return "teamtailor"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db_boards = [
            TeamtailorBoard(
                company=c.get("company", c.get("career_url", "")),
                career_url=c["career_url"],
            )
            for c in self._load_db_config()
            if "career_url" in c
        ]
        boards = self.boards + db_boards
        all_raw: List[Dict[str, Any]] = []

        for board in boards:
            url = f"{board.career_url.rstrip('/')}/jobs.json"
            try:
                resp = self._http.get(url, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Teamtailor fetch error [%s]: %s", board.company, e)
                continue

            data = resp.json()
            items = data.get("items", [])
            for item in items:
                item["_board"] = board
            all_raw.extend(items)
            logger.info("Fetched %d jobs from %s", len(items), board.company)

        return all_raw

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        board: TeamtailorBoard = raw_job["_board"]
        jp: Dict[str, Any] = raw_job.get("_jobposting") or {}

        identifier = jp.get("identifier") or {}
        job_id = str(identifier.get("value") or raw_job.get("id") or "")
        title = raw_job.get("title") or jp.get("title") or ""

        description_html = jp.get("description") or raw_job.get("content_html") or ""
        description = _strip_html(description_html)[:5000] if description_html else None

        location_city, country_code = _parse_location(jp.get("jobLocation"))

        remote = _parse_remote(jp)

        date_str = raw_job.get("date_published") or jp.get("datePosted") or ""
        posted_date = _parse_date(date_str)

        apply_url = raw_job.get("url") or board.career_url

        return {
            "source_job_id": f"{_slug(board.company)}:{job_id}",
            "title": title,
            "company": board.company,
            "department": None,
            "location": location_city,
            "remote": remote,
            "country": country_code,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "company_industry": "Technology",
            "company_size": "Mid-size (500-1k)",
            "source_type": "company_portal",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_location(
    job_location: Optional[Any],
) -> tuple:
    """Extract (city, country_code) from Schema.org jobLocation list."""
    if not job_location:
        return None, None
    if isinstance(job_location, list):
        job_location = job_location[0] if job_location else {}
    addr = job_location.get("address") or {}
    city = addr.get("addressLocality") or None
    country = (addr.get("addressCountry") or "").lower() or None
    return city, country


def _parse_remote(jp: Dict[str, Any]) -> Optional[str]:
    """Infer remote/hybrid/onsite from Schema.org fields."""
    # jobLocationType: TELECOMMUTE means fully remote
    loc_type = (jp.get("jobLocationType") or "").upper()
    if loc_type == "TELECOMMUTE":
        return "remote"
    # Fall back to keyword scan on employment type or title
    title = (jp.get("title") or "").lower()
    desc = (jp.get("description") or "").lower()[:500]
    if "hybrid" in title or "hybrid" in desc:
        return "hybrid"
    if "remote" in title or "remote" in desc:
        return "remote"
    return None


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.utcnow()
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return datetime.utcnow()


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
