"""Innovair IRV job scraper.

Innova-IRV (https://innovairv.com) is a microelectronics research institute
based in Málaga, Spain. Job listings are published directly in the careers
page HTML — no separate API.

Listing page: https://innovairv.com/en/careers/
Structure:
  div.grid__empleos
    div.grid__block          ← one per job
      h3.block__title        ← job title
      div.block__texto       ← description snippet
      div.btn-block > a.btn  ← individual job page URL (/en/empleos/{slug}/)

source_job_id is the slug extracted from the job URL.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.innovairv")

CAREERS_URL = "https://innovairv.com/en/careers/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class InnovaIRVScraper(BaseScraper):
    """Scraper for Innova-IRV's careers page."""

    def _get_source_name(self) -> str:
        return "innovairv"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        try:
            resp = requests.get(CAREERS_URL, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Failed to fetch Innova-IRV careers page: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        blocks = soup.select("div.grid__block")
        logger.info("Found %d job blocks on Innova-IRV careers page", len(blocks))
        return [{"_block": str(block)} for block in blocks]

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        soup = BeautifulSoup(raw_job["_block"], "html.parser")

        title_tag = soup.select_one("h3.block__title")
        title = title_tag.get_text(strip=True) if title_tag else None
        if not title:
            return {}

        link_tag = soup.select_one("div.btn-block a.btn")
        apply_url = (
            link_tag["href"] if link_tag and link_tag.get("href") else CAREERS_URL
        )

        # Derive stable ID from URL slug, fall back to slugified title
        slug_match = re.search(r"/empleos/([^/]+)/?$", apply_url)
        source_job_id = (
            slug_match.group(1)
            if slug_match
            else re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        )

        desc_tag = soup.select_one("div.block__texto")
        description = None
        if desc_tag:
            description = re.sub(
                r"\s+", " ", desc_tag.get_text(separator=" ", strip=True)
            )

        return {
            "source_job_id": source_job_id,
            "title": title,
            "company": "Innova-IRV",
            "location": "Málaga, Spain",
            "country": "ES",
            "remote": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": datetime.now(timezone.utc),
            "salary_min": None,
            "salary_max": None,
            "company_industry": "Semiconductors / Microelectronics",
            "company_size": "Small (<200)",
            "source_type": "company_portal",
        }
