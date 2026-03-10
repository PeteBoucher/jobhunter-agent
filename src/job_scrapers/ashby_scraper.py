"""Ashby job board scraper.

Ashby is an ATS used by many modern startups and scale-ups.
Their job board API is publicly accessible and returns JSON data.

API endpoint: https://api.ashbyhq.com/posting-api/job-board/{slug}
No authentication required.
"""

import logging
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
    # Smaller but relevant
    "airbyte",
    "neon",
    "railway",
    "prefect",
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
        board_slugs = kwargs.get("board_slugs", self.board_slugs)
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

        # Determine remote status; workplaceType is authoritative over isRemote
        # because Ashby can set isRemote=true on hybrid jobs.
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

        department = raw_job.get("department") or raw_job.get("team")

        # Prefer plain text description, fall back to stripping HTML
        description = raw_job.get("descriptionPlain", "") or ""
        if not description:
            html = raw_job.get("descriptionHtml", "") or ""
            description = self._strip_html(html)

        # Parse published date
        posted_date = datetime.utcnow()
        published_at = raw_job.get("publishedAt")
        if published_at:
            try:
                posted_date = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

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
            "description": description[:5000] if description else None,
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
        import re

        if not html:
            return ""
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
