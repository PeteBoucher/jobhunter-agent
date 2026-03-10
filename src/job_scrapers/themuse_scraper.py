"""The Muse job board scraper.

The Muse provides a free public API with curated job listings from
well-known tech companies. No authentication required.

API docs: https://www.themuse.com/developers/api/v2
Endpoint: https://www.themuse.com/api/public/jobs
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.themuse")

THEMUSE_API_URL = "https://www.themuse.com/api/public/jobs"

DEFAULT_CATEGORIES = [
    "Management",
    "Software Engineering",
]


class TheMuseScraper(BaseScraper):
    """Scraper for The Muse job listings API.

    Fetches curated job listings from well-known companies.
    The API is public and requires no authentication.
    """

    def __init__(
        self,
        session: Session,
        categories: Optional[List[str]] = None,
    ):
        super().__init__(session)
        self.categories = categories or DEFAULT_CATEGORIES

    def _get_source_name(self) -> str:
        return "themuse"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from The Muse API.

        Kwargs:
            max_pages: Max pages to fetch (default: 10)
            categories: Override default category list

        Returns:
            List of raw job dicts from The Muse API
        """
        max_pages = kwargs.get("max_pages", 10)
        categories = kwargs.get("categories", self.categories)

        all_jobs: List[Dict[str, Any]] = []

        for page in range(max_pages):
            try:
                params: Dict[str, Any] = {
                    "page": page,
                    "descending": "true",
                }
                # Add category filters
                for cat in categories:
                    params.setdefault("category", [])
                    if isinstance(params["category"], list):
                        params["category"].append(cat)

                resp = requests.get(THEMUSE_API_URL, params=params, timeout=15)

                if resp.status_code != 200:
                    logger.warning(
                        f"The Muse API error page {page}: HTTP {resp.status_code}"
                    )
                    break

                data = resp.json()
                results = data.get("results", [])

                if not results:
                    break

                all_jobs.extend(results)
                logger.info(f"Fetched {len(results)} jobs from The Muse (page {page})")

                # Check if there are more pages
                total_pages = data.get("page_count", 0)
                if page >= total_pages - 1:
                    break

            except requests.RequestException as e:
                logger.warning(f"Failed to fetch from The Muse: {e}")
                break

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Muse API job object into standardized format."""
        # Extract locations
        locations = raw_job.get("locations", [])
        location = None
        if locations:
            location = (
                locations[0].get("name") if isinstance(locations[0], dict) else None
            )

        # Determine remote status
        remote = None
        if location:
            loc_lower = location.lower()
            if "remote" in loc_lower or "flexible" in loc_lower:
                remote = "remote"

        # Company info
        company_data = raw_job.get("company", {})
        company = (
            company_data.get("name", "Unknown")
            if isinstance(company_data, dict)
            else "Unknown"
        )
        company_size = (
            company_data.get("size", {}) if isinstance(company_data, dict) else {}
        )
        size_label = (
            company_size.get("name") if isinstance(company_size, dict) else None
        )
        industry_data = (
            company_data.get("industries", []) if isinstance(company_data, dict) else []
        )
        industry = (
            industry_data[0].get("name")
            if industry_data and isinstance(industry_data[0], dict)
            else None
        )

        # Extract categories as department
        categories = raw_job.get("categories", [])
        department = (
            categories[0].get("name")
            if categories and isinstance(categories[0], dict)
            else None
        )

        # Strip HTML from contents
        contents = raw_job.get("contents", "")
        description = self._strip_html(contents)

        # Parse date
        posted_date = datetime.utcnow()
        pub_date = raw_job.get("publication_date")
        if pub_date:
            try:
                posted_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Build apply URL
        refs = raw_job.get("refs", {})
        apply_url = refs.get("landing_page", "") if isinstance(refs, dict) else ""

        return {
            "source_job_id": str(raw_job.get("id", "")),
            "title": raw_job.get("name", ""),
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
            "company_industry": industry,
            "company_size": size_label,
            "source_type": "aggregator",
        }

    @staticmethod
    def _strip_html(html: str) -> str:
        """Strip HTML tags from a string."""
        if not html:
            return ""
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
