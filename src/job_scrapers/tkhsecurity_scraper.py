"""TKH Security job scraper.

TKH Security (https://tkhsecurity.com) is a security systems company based in
the Netherlands. Job listings are published directly in the careers page HTML
using a WordPress plugin (wombat-career) — no separate API.

Listing page: https://tkhsecurity.com/vacancies/ (redirects to /careers/)
Structure:
  div.b-career-api
    div.b-career-api__list
      a.job-item                   ← one per job; href contains ?id=<id>
        h5.job-item__title         ← job title
        span.job-item__term        ← job category
        div.job-item__meta-group   ← two <span>s: city and country

source_job_id is extracted from the job URL query parameter (id={id}).
Jobs are in multiple countries (NL, ES, …) so country is inferred by the
base class rather than hardcoded.
"""

import logging
import re
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.tkhsecurity")

CAREERS_URL = "https://tkhsecurity.com/vacancies/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class TKHSecurityScraper(BaseScraper):
    """Scraper for TKH Security's careers page."""

    def __init__(self, session: Session):
        super().__init__(session)
        self._http = requests.Session()
        self._http.headers.update(_HEADERS)

    def _get_source_name(self) -> str:
        return "tkhsecurity"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        try:
            resp = self._http.get(CAREERS_URL, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to fetch TKH Security careers page: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        job_items = soup.select("a.job-item")
        logger.info("tkhsecurity jobs=%d", len(job_items))
        return [{"_item": str(item)} for item in job_items]

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        soup = BeautifulSoup(raw_job["_item"], "html.parser")

        title_tag = soup.select_one("h5.job-item__title")
        title = title_tag.get_text(strip=True) if title_tag else None
        if not title:
            return {}

        # The raw item IS the <a> element, so href is on the root tag
        link_tag = soup.find("a")
        apply_url = link_tag.get("href", CAREERS_URL) if link_tag else CAREERS_URL

        id_match = re.search(r"[?&]id=(\d+)", apply_url)
        source_job_id = (
            id_match.group(1)
            if id_match
            else re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        )

        # Location: two spans — city (with trailing comma) and country name
        meta_group = soup.select_one("div.job-item__meta-group")
        location = None
        if meta_group:
            parts = [
                s.get_text(strip=True).rstrip(",") for s in meta_group.select("span")
            ]
            location = ", ".join(p for p in parts if p) or None

        return {
            "source_job_id": source_job_id,
            "title": title,
            "company": "TKH Security",
            "location": location,
            "country": None,  # inferred by base class from location
            "remote": None,
            "description": None,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": None,
            "salary_min": None,
            "salary_max": None,
            "company_industry": "Security Systems",
            "company_size": "Large",
            "source_type": "company_portal",
        }
