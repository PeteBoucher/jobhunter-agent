"""Reed.co.uk job board scraper.

Reed is the UK's largest job board and has strong coverage of non-SWE roles
including Innovation, Enterprise Architecture, QA, and Digital Transformation.

API docs: https://www.reed.co.uk/developers/jobseeker
Endpoint: https://www.reed.co.uk/api/1.0/search

Authentication: HTTP Basic Auth with API key as username, empty password.
Get a free key at: https://www.reed.co.uk/developers
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.reed")

REED_API_BASE = "https://www.reed.co.uk/api/1.0"

# Broad search terms covering common tech, product, and leadership roles.
DEFAULT_SEARCH_TERMS = [
    "software engineer",
    "product manager",
    "engineering manager",
    "data engineer",
    "devops engineer",
    "frontend developer",
    "backend developer",
    "qa engineer",
    "solutions architect",
    "digital transformation",
]

RESULTS_PER_PAGE = 100


class ReedScraper(BaseScraper):
    """Scraper for Reed.co.uk job listings API.

    Fetches jobs using Reed's JobSeeker API. Covers UK and remote roles
    with strong representation of non-engineering leadership positions.
    Requires a free API key from https://www.reed.co.uk/developers.
    """

    def __init__(
        self,
        session: Session,
        api_key: Optional[str] = None,
        search_terms: Optional[List[str]] = None,
    ):
        super().__init__(session)
        self.api_key = api_key or os.environ.get("REED_API_KEY", "")
        self.search_terms = search_terms or DEFAULT_SEARCH_TERMS

    def _get_source_name(self) -> str:
        return "reed"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from Reed API across all configured search terms.

        Kwargs:
            search_terms: Override default search terms list
            max_results_per_term: Max results per search term (default: 100)

        Returns:
            List of raw job dicts from the Reed API (deduplicated by job ID)
        """
        if not self.api_key:
            logger.warning(
                "Reed API key not configured. "
                "Set REED_API_KEY environment variable. "
                "Get a free key at https://www.reed.co.uk/developers"
            )
            return []

        search_terms = kwargs.get("search_terms", self.search_terms)
        max_results_per_term = kwargs.get("max_results_per_term", RESULTS_PER_PAGE)

        seen_ids: set = set()
        all_jobs: List[Dict[str, Any]] = []

        for term in search_terms:
            results_to_skip = 0
            while True:
                try:
                    url = f"{REED_API_BASE}/search"
                    params = {
                        "keywords": term,
                        "resultsToTake": RESULTS_PER_PAGE,
                        "resultsToSkip": results_to_skip,
                    }

                    resp = requests.get(
                        url,
                        params=params,
                        auth=(self.api_key, ""),
                        timeout=15,
                    )

                    if resp.status_code == 401:
                        logger.warning("Reed API authentication failed")
                        return all_jobs
                    if resp.status_code == 429:
                        logger.warning("Reed API rate limit reached")
                        return all_jobs
                    if resp.status_code != 200:
                        logger.warning(
                            f"Reed API error for '{term}': HTTP {resp.status_code}"
                        )
                        break

                    data = resp.json()
                    results = data.get("results", [])

                    if not results:
                        break

                    new_results = []
                    for job in results:
                        job_id = job.get("jobId")
                        if job_id not in seen_ids:
                            seen_ids.add(job_id)
                            new_results.append(job)

                    all_jobs.extend(new_results)
                    logger.info(
                        f"Fetched {len(new_results)} jobs from Reed ('{term}', "
                        f"skip={results_to_skip})"
                    )

                    results_to_skip += len(results)
                    if (
                        results_to_skip >= max_results_per_term
                        or len(results) < RESULTS_PER_PAGE
                    ):
                        break

                except requests.RequestException as e:
                    logger.warning(f"Failed to fetch from Reed ('{term}'): {e}")
                    break

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Reed API job object into standardized format."""
        title = raw_job.get("jobTitle", "")
        location = raw_job.get("locationName")

        # Determine remote status
        remote = None
        description = raw_job.get("jobDescription", "") or ""
        combined = f"{title} {location or ''} {description}".lower()
        if "remote" in combined:
            remote = "remote"
        elif "hybrid" in combined:
            remote = "hybrid"

        # Parse salary
        salary_min = raw_job.get("minimumSalary")
        salary_max = raw_job.get("maximumSalary")

        # Parse date
        posted_date = datetime.utcnow()
        date_str = raw_job.get("date")
        if date_str:
            try:
                posted_date = datetime.strptime(date_str, "%d/%m/%Y")
            except (ValueError, TypeError):
                try:
                    posted_date = datetime.fromisoformat(date_str)
                except (ValueError, TypeError):
                    pass

        apply_url = raw_job.get("jobUrl", "")

        return {
            "source_job_id": str(raw_job.get("jobId", "")),
            "title": title,
            "company": raw_job.get("employerName", "Unknown"),
            "department": None,
            "location": location,
            "remote": remote,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": description[:5000] if description else None,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "company_industry": None,
            "company_size": None,
            "source_type": "aggregator",
        }
