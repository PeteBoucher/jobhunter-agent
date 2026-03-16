"""Thoughtworks careers scraper.

Uses the undocumented REST API that powers https://www.thoughtworks.com/careers/jobs.
Returns all open roles in a single request — no pagination, no auth required.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers")

_API_URL = "https://www.thoughtworks.com/rest/careers/jobs"
_JOB_BASE_URL = "https://www.thoughtworks.com/careers/jobs/job"


class ThoughtworksScraper(BaseScraper):
    """Scraper for Thoughtworks open roles.

    Fetches all jobs from the careers REST API in a single call.
    Server-side filtering is not supported; deduplication is handled by
    BaseScraper via source_job_id.
    """

    def __init__(self, session: Session):
        super().__init__(session)

    def _get_source_name(self) -> str:
        return "thoughtworks"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        resp = requests.get(_API_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("jobs", [])

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(raw_job.get("sourceSystemId", ""))
        location = raw_job.get("location") or raw_job.get("country") or ""
        remote: Optional[str] = "remote" if raw_job.get("remoteEligible") else None

        updated_at = raw_job.get("updatedAt")
        try:
            posted_date = (
                datetime.fromisoformat(updated_at) if updated_at else datetime.utcnow()
            )
        except (ValueError, TypeError):
            posted_date = datetime.utcnow()

        return {
            "source_job_id": job_id,
            "title": raw_job.get("name"),
            "company": "Thoughtworks",
            "department": raw_job.get("role"),
            "location": location,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": None,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": f"{_JOB_BASE_URL}/{job_id}" if job_id else _JOB_BASE_URL,
            "posted_date": posted_date,
            "company_industry": "Technology Consulting",
            "company_size": "Large",
            "source_type": "company_portal",
        }
