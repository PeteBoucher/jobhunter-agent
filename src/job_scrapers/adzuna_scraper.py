"""Adzuna job aggregator scraper.

Adzuna aggregates jobs from Indeed, Reed, Monster, and other job boards.
Their API is publicly accessible with a free API key from developer.adzuna.com.

API docs: https://developer.adzuna.com/docs/search
Endpoint: https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.adzuna")

ADZUNA_API_BASE = "https://api.adzuna.com/v1/api/jobs"

# Maps location substrings (lowercase) to Adzuna country codes.
LOCATION_TO_COUNTRY_CODE = {
    "uk": "gb",
    "united kingdom": "gb",
    "england": "gb",
    "london": "gb",
    "scotland": "gb",
    "wales": "gb",
    "ireland": "ie",
    "spain": "es",
    "france": "fr",
    "germany": "de",
    "netherlands": "nl",
    "portugal": "pt",
    "italy": "it",
    "canada": "ca",
    "australia": "au",
    "new zealand": "nz",
    "united states": "us",
    "usa": "us",
}


class AdzunaScraper(BaseScraper):
    """Scraper for Adzuna job aggregator API.

    Fetches jobs from Adzuna which aggregates listings from Indeed, Reed,
    Monster, and many other job boards. Requires a free API key.
    """

    def __init__(
        self,
        session: Session,
        countries: Optional[List[str]] = None,
        search_terms: Optional[List[str]] = None,
        app_id: Optional[str] = None,
        app_key: Optional[str] = None,
    ):
        super().__init__(session)
        self.countries = countries or self._countries_from_prefs(
            LOCATION_TO_COUNTRY_CODE, fallback=["gb", "es"]
        )
        self.search_terms = search_terms or self._search_terms_from_prefs()
        self.app_id = app_id or os.environ.get("ADZUNA_APP_ID", "")
        self.app_key = app_key or os.environ.get("ADZUNA_APP_KEY", "")

    def _get_source_name(self) -> str:
        return "adzuna"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from Adzuna API across configured countries and search terms.

        Kwargs:
            search_terms: Override default search terms list
            max_pages: Max pages per country/term combination (default: 3)
            results_per_page: Results per page (default: 50)

        Returns:
            List of raw job dicts from the Adzuna API (deduplicated by job ID)
        """
        if not self.app_id or not self.app_key:
            logger.warning(
                "Adzuna API credentials not configured. "
                "Set ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables."
            )
            return []

        search_terms = kwargs.get("search_terms", self.search_terms)
        max_pages = kwargs.get("max_pages", 3)
        results_per_page = kwargs.get("results_per_page", 50)

        seen_ids: set = set()
        all_jobs: List[Dict[str, Any]] = []

        for country in self.countries:
            for term in search_terms:
                for page in range(1, max_pages + 1):
                    try:
                        url = f"{ADZUNA_API_BASE}/{country}/search/{page}"
                        params = {
                            "app_id": self.app_id,
                            "app_key": self.app_key,
                            "results_per_page": results_per_page,
                            "what_phrase": term,
                            "content-type": "application/json",
                        }

                        resp = requests.get(url, params=params, timeout=15)

                        if resp.status_code == 401:
                            logger.warning("Adzuna API authentication failed")
                            return all_jobs
                        if resp.status_code == 429:
                            logger.warning("Adzuna API rate limit reached")
                            return all_jobs
                        if resp.status_code != 200:
                            logger.warning(
                                f"Adzuna API error for {country}/{term} page {page}: "
                                f"HTTP {resp.status_code}"
                            )
                            break

                        data = resp.json()
                        results = data.get("results", [])

                        if not results:
                            break

                        new_results = []
                        for job in results:
                            job_id = job.get("id")
                            if job_id not in seen_ids:
                                seen_ids.add(job_id)
                                job["_country"] = country
                                new_results.append(job)

                        all_jobs.extend(new_results)
                        logger.info(
                            f"Fetched {len(new_results)} jobs from Adzuna "
                            f"({country}, '{term}', page {page})"
                        )

                        # Stop if we got fewer results than requested (last page)
                        if len(results) < results_per_page:
                            break

                    except requests.RequestException as e:
                        logger.warning(
                            f"Failed to fetch from Adzuna ({country}/{term}): {e}"
                        )
                        break

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse an Adzuna API job object into standardized format."""
        # Extract location
        location = raw_job.get("location", {})
        location_parts = (
            location.get("display_name", "") if isinstance(location, dict) else ""
        )

        # Determine remote status
        remote = None
        title = raw_job.get("title", "")
        if location_parts:
            combined = f"{title} {location_parts}".lower()
            if "remote" in combined:
                remote = "remote"
            elif "hybrid" in combined:
                remote = "hybrid"

        # Parse salary
        salary_min = raw_job.get("salary_min")
        salary_max = raw_job.get("salary_max")
        if salary_min is not None:
            salary_min = int(salary_min)
        if salary_max is not None:
            salary_max = int(salary_max)

        # Parse date
        posted_date = datetime.utcnow()
        created = raw_job.get("created")
        if created:
            try:
                posted_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Extract description (plain text from Adzuna)
        description = raw_job.get("description", "")

        # Company
        company_data = raw_job.get("company", {})
        company = (
            company_data.get("display_name", "Unknown")
            if isinstance(company_data, dict)
            else "Unknown"
        )

        # Category
        category = raw_job.get("category", {})
        department = category.get("label") if isinstance(category, dict) else None

        return {
            "source_job_id": str(raw_job.get("id", "")),
            "title": title,
            "company": company,
            "department": department,
            "location": location_parts or None,
            "remote": remote,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": description[:5000] if description else None,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": raw_job.get("redirect_url", ""),
            "posted_date": posted_date,
            "company_industry": None,
            "company_size": None,
            "source_type": "aggregator",
        }
