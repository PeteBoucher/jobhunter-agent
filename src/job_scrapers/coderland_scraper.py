"""Coderland job board scraper.

Coderland is a LATAM IT staffing company. Their careers page
(https://www.coderland.com/en/work-us) is powered by Manatal ATS, proxied
through a Next.js API route that returns JSON without authentication.

API endpoint (GET):
  https://www.coderland.com/api/v1/career-page-jobs?language=en&page=N

Response shape:
  { currentPage, data: [...], hasNextPage, pages, perPage, totalRecords }

Job fields used: id, title, description (HTML), mode, technologies,
  responsibilities, requires
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.coderland")

CODERLAND_API = "https://www.coderland.com/api/v1/career-page-jobs"
CODERLAND_JOB_URL = "https://www.coderland.com/en/work-us"


class CodelandScraper(BaseScraper):
    """Scraper for Coderland's Manatal-backed careers page."""

    def __init__(self, session: Session):
        super().__init__(session)
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
        return "coderland"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        # The API ignores page/offset — perPage=200 fetches all in one request.
        try:
            resp = self._http.get(
                CODERLAND_API,
                params={"language": "en", "perPage": "200"},
                timeout=15,
            )
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Coderland API error: %s", e)
            return []

        data = resp.json()
        jobs = data.get("data", [])
        logger.info("Fetched %d jobs from Coderland", len(jobs))
        return jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(raw_job.get("id", ""))
        title = raw_job.get("title") or raw_job.get("position") or ""
        description_html = raw_job.get("description") or ""
        description = _strip_html(description_html)[:5000] if description_html else None

        # `requires` is a list of plain-text requirement strings.
        # `responsibilities` duplicates the description HTML — skip it.
        requires = [_strip_html(r) for r in (raw_job.get("requires") or []) if r]
        requirements = "; ".join(requires) if requires else None

        technologies = raw_job.get("technologies") or []
        nice_to_haves = ", ".join(technologies) if technologies else None

        mode_raw = (raw_job.get("mode") or "").lower()
        if "hybrid" in mode_raw:
            remote = "hybrid"
        elif "remote" in mode_raw:
            remote = "remote"
        else:
            remote = None

        return {
            "source_job_id": job_id,
            "title": title,
            "company": "Coderland",
            "department": None,
            "location": None,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": nice_to_haves,
            "apply_url": f"{CODERLAND_JOB_URL}/{job_id}",
            "posted_date": datetime.utcnow(),
            "company_industry": "IT Staffing / Technology",
            "company_size": "Mid-size (500-1k)",
            "source_type": "company_portal",
        }


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean
