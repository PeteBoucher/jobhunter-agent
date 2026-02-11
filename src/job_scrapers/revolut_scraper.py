"""Revolut careers scraper (stub).

This is a minimal scraper stub for Revolut's careers portal.
Most company career portals require dynamic JS or authenticated APIs; this
stub returns an empty list by default and follows the BaseScraper interface.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper


class RevolutScraper(BaseScraper):
    """Scraper for Revolut careers portal (careers.revolut.com).

    This is a conservative stub that returns no results by default. Replace
    the fetch logic with a requests/selenium/playwright-based implementation
    if needed.
    """

    REVOLUT_CAREERS = "https://careers.revolut.com"

    def __init__(self, session: Session):
        super().__init__(session)

    def _get_source_name(self) -> str:
        return "revolut"

    def _fetch_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 0,
        page_size: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        # Revolut careers page is dynamic; implement a real fetch if required.
        return []

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        posted_date = datetime.utcnow()
        return {
            "source_job_id": raw_job.get("id"),
            "title": raw_job.get("title"),
            "company": "Revolut",
            "department": raw_job.get("team"),
            "location": raw_job.get("location"),
            "remote": raw_job.get("remote"),
            "salary_min": None,
            "salary_max": None,
            "description": raw_job.get("description"),
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": raw_job.get("apply_url") or self.REVOLUT_CAREERS,
            "posted_date": posted_date,
            "company_industry": "Fintech",
            "company_size": "Medium-Large",
            "source_type": "company_portal",
        }
