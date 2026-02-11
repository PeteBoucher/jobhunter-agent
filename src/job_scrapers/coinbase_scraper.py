"""Coinbase careers scraper (stub).

Minimal stub for Coinbase careers (careers.coinbase.com). Returns empty
results by default; extend `_fetch_jobs` with real HTTP or headless browser
logic as needed.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper


class CoinbaseScraper(BaseScraper):
    COINBASE_CAREERS = "https://careers.coinbase.com"

    def __init__(self, session: Session):
        super().__init__(session)

    def _get_source_name(self) -> str:
        return "coinbase"

    def _fetch_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 0,
        page_size: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        # Coinbase careers may require API or dynamic rendering; return empty
        # placeholder so the rest of the system can register the source.
        return []

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        posted_date = datetime.utcnow()
        return {
            "source_job_id": raw_job.get("id"),
            "title": raw_job.get("title"),
            "company": "Coinbase",
            "department": raw_job.get("team"),
            "location": raw_job.get("location"),
            "remote": raw_job.get("remote"),
            "salary_min": None,
            "salary_max": None,
            "description": raw_job.get("description"),
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": raw_job.get("apply_url") or self.COINBASE_CAREERS,
            "posted_date": posted_date,
            "company_industry": "Fintech",
            "company_size": "Large",
            "source_type": "company_portal",
        }
