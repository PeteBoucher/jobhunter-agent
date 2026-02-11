"""Uber careers scraper (stub).

Stub for Uber careers portal (www.uber.com/us/en/careers). Returns empty results
by default and provides a parser scaffold for future implementation.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper


class UberScraper(BaseScraper):
    UBER_CAREERS = "https://www.uber.com/us/en/careers"

    def __init__(self, session: Session):
        super().__init__(session)

    def _get_source_name(self) -> str:
        return "uber"

    def _fetch_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 0,
        page_size: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        # Uber careers uses dynamic content; implement fetch with headless
        # browser or use their public jobs API if available.
        return []

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        posted_date = datetime.utcnow()
        return {
            "source_job_id": raw_job.get("id"),
            "title": raw_job.get("title"),
            "company": "Uber",
            "department": raw_job.get("team"),
            "location": raw_job.get("location"),
            "remote": raw_job.get("remote"),
            "salary_min": None,
            "salary_max": None,
            "description": raw_job.get("description"),
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": raw_job.get("apply_url") or self.UBER_CAREERS,
            "posted_date": posted_date,
            "company_industry": "Transportation/Tech",
            "company_size": "Large",
            "source_type": "company_portal",
        }
