"""Ashby job board scraper.

Ashby is an ATS used by many modern startups and scale-ups.
Their job board API is publicly accessible and returns JSON data.

API endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}
No authentication required.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.ashby")

# Companies using Ashby with confirmed job listings.
# Covers modern startups, fintech, AI/ML, infra, and European scale-ups.
DEFAULT_BOARD_SLUGS = [
    # High-volume boards (100+ jobs)
    "openai",
    "notion",
    "deel",
    "ramp",
    "cohere",
    "deliveroo",
    "plaid",
    "elevenlabs",
    "replit",
    "synthesia",
    "cursor",
    "perplexity",
    # Mid-volume boards (20-100 jobs)
    "clickup",
    "confluent",
    "1password",
    "linear",
    "zapier",
    "supabase",
    "sanity",
    "render",
    "runway-ml",
    "benchling",
    "mollie",
    "paddle",
    "primer",
    # Smaller but relevant
    "airbyte",
    "neon",
    "railway",
    "prefect",
    "wayflyer",
    "posthog",
    "plain",
    "browserbase",
    "warp",
    "orb",
]

ASHBY_API_BASE = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyScraper(BaseScraper):
    """Scraper for Ashby-hosted job boards.

    Fetches jobs from multiple companies that use Ashby as their ATS.
    The API is public and requires no authentication.
    """

    def __init__(self, session: Session, board_slugs: Optional[List[str]] = None):
        super().__init__(session)
        self.board_slugs = board_slugs or DEFAULT_BOARD_SLUGS

    def _get_source_name(self) -> str:
        return "ashby"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from all configured Ashby boards.

        Kwargs:
            board_slugs: Override default board slugs list

        Returns:
            List of raw job dicts from the Ashby API
        """
        db_slugs = [c["subdomain"] for c in self._load_db_config() if "subdomain" in c]
        board_slugs = kwargs.get("board_slugs") or (self.board_slugs + db_slugs)
        all_jobs: List[Dict[str, Any]] = []

        for slug in board_slugs:
            try:
                url = f"{ASHBY_API_BASE}/{slug}"
                resp = requests.get(url, timeout=15)

                if resp.status_code == 404:
                    logger.debug(f"Board not found: {slug}")
                    continue
                if resp.status_code != 200:
                    logger.warning(
                        f"Ashby API error for {slug}: HTTP {resp.status_code}"
                    )
                    continue

                data = resp.json()
                jobs = data.get("jobs", [])

                # Only include listed jobs
                jobs = [j for j in jobs if j.get("isListed", True)]

                # Tag each job with the board slug
                for job in jobs:
                    job["_board_slug"] = slug

                all_jobs.extend(jobs)
                logger.info(f"Fetched {len(jobs)} jobs from {slug}")

            except requests.RequestException as e:
                logger.warning(f"Failed to fetch from {slug}: {e}")
                continue

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse an Ashby API job object into standardized format."""
        board_slug = raw_job.get("_board_slug", "unknown")

        location = raw_job.get("location")
        details = parse_ashby_details(raw_job)
        department = raw_job.get("department") or raw_job.get("team")
        description = details["description"]
        remote = details["remote"]
        posted_date = details["posted_date"] or datetime.utcnow()

        apply_url = raw_job.get("applyUrl") or raw_job.get("jobUrl", "")
        company = board_slug.replace("-", " ").title()

        return {
            "source_job_id": str(raw_job.get("id", "")),
            "title": raw_job.get("title", ""),
            "company": company,
            "department": department,
            "location": location,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "company_industry": "Technology",
            "company_size": None,
            "source_type": "company_portal",
        }

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags from a string."""
        return _strip_html(html)


def _strip_html(html: Optional[str]) -> str:
    if not html:
        return ""
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def fetch_ashby_board(slug: str, http: Any = requests) -> List[Dict[str, Any]]:
    """Return the listed jobs on one Ashby board (raises on HTTP errors).

    `http` is anything with a requests-style `.get()` (module or Session).
    """
    resp = http.get(f"{ASHBY_API_BASE}/{slug}", timeout=15)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])
    return [j for j in jobs if j.get("isListed", True)]


def parse_ashby_details(raw_job: Dict[str, Any]) -> Dict[str, Any]:
    """Extract remote status, description and posted date from an Ashby job.

    Shared by `AshbyScraper` and aggregators that link to Ashby postings
    (GibWork), so both read Ashby data the same way. `posted_date` is None
    when `publishedAt` is missing or unparseable; `description` is None when
    empty.
    """
    location = raw_job.get("location")

    # workplaceType is authoritative over isRemote because Ashby can set
    # isRemote=true on hybrid jobs.
    remote = None
    workplace_type = (raw_job.get("workplaceType") or "").lower()
    if "hybrid" in workplace_type:
        remote = "hybrid"
    elif "remote" in workplace_type or raw_job.get("isRemote"):
        remote = "remote"
    elif location and "hybrid" in location.lower():
        remote = "hybrid"
    elif location and "remote" in location.lower():
        remote = "remote"

    # Prefer plain text description, fall back to stripping HTML
    description = raw_job.get("descriptionPlain") or _strip_html(
        raw_job.get("descriptionHtml")
    )

    posted_date: Optional[datetime] = None
    published_at = raw_job.get("publishedAt")
    if published_at:
        try:
            posted_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            pass

    return {
        "remote": remote,
        "description": description[:5000] if description else None,
        "posted_date": posted_date,
    }
