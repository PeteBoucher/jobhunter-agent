"""LinkedIn jobs scraper.

Uses LinkedIn's public guest search endpoint which returns HTML fragments.
Selectors are based on the current layout (verified Feb 2026) but may drift
over time as LinkedIn updates their frontend.
"""
import logging
import random
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.linkedin")

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
]

DEFAULT_SEARCH_TERMS = [
    "innovation lead",
    "enterprise architect",
    "quality assurance lead",
    "digital transformation",
    "agile coach",
]

DEFAULT_LOCATION = "United Kingdom"


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn jobs (public guest search endpoint).

    Fetches job cards from LinkedIn's unauthenticated search API across
    multiple search terms and deduplicates by job posting ID.

    Notes:
    - Returns HTML fragments; selectors may break if LinkedIn redesigns.
    - Backs off on 429 and returns results collected so far.
    - Adds a 1 s delay between pages to avoid rate limiting.
    """

    LINKEDIN_SEARCH_API = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    )

    def __init__(
        self,
        session: Session,
        search_terms: Optional[List[str]] = None,
        location: str = DEFAULT_LOCATION,
    ):
        super().__init__(session)
        self.search_terms = search_terms or DEFAULT_SEARCH_TERMS
        self.location = location

    def _get_source_name(self) -> str:
        return "linkedin"

    def _fetch_jobs(self, max_pages: int = 2, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from LinkedIn across all configured search terms.

        Paginates each term (25 results/page) and deduplicates across terms
        by LinkedIn job posting ID extracted from the data-entity-urn attribute.

        Returns:
            List of raw job dicts (already in standard format; _parse_job is
            identity for this scraper).
        """
        seen_ids: set = set()
        all_results: List[Dict[str, Any]] = []

        for term in self.search_terms:
            for page in range(max_pages):
                params = {
                    "keywords": term,
                    "location": self.location,
                    "start": str(page * 25),
                }
                headers = {
                    "User-Agent": random.choice(_USER_AGENTS),
                    "Accept": (
                        "text/html,application/xhtml+xml,"
                        "application/xml;q=0.9,*/*;q=0.8"
                    ),
                }

                try:
                    resp = requests.get(
                        self.LINKEDIN_SEARCH_API,
                        params=params,
                        headers=headers,
                        timeout=10,
                    )

                    if resp.status_code == 429:
                        wait = 2 ** (page + 1)
                        logger.warning(
                            f"LinkedIn rate limited on '{term}' p{page}, "
                            f"backing off {wait}s"
                        )
                        time.sleep(wait)
                        return all_results

                    if resp.status_code != 200:
                        logger.warning(
                            f"LinkedIn returned {resp.status_code} for '{term}'"
                        )
                        break

                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("div", class_="base-card")

                    if not cards:
                        break

                    parsed_any = False
                    for card in cards:
                        # Job ID from data-entity-urn="urn:li:jobPosting:1234"
                        urn = card.get("data-entity-urn", "")
                        job_id = urn.split(":")[-1] if urn else None
                        if not job_id or job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        title_tag = card.find("h3", class_="base-search-card__title")
                        title = title_tag.get_text(strip=True) if title_tag else None

                        company_tag = card.find(
                            "h4", class_="base-search-card__subtitle"
                        )
                        company = (
                            company_tag.get_text(strip=True) if company_tag else None
                        )

                        loc_tag = card.find("span", class_="job-search-card__location")
                        loc = loc_tag.get_text(strip=True) if loc_tag else None

                        link_tag = card.find("a", class_="base-card__full-link")
                        href = (
                            link_tag["href"].split("?")[0]
                            if link_tag and link_tag.get("href")
                            else None
                        )

                        posted_date = datetime.utcnow()
                        time_tag = card.find("time", class_="job-search-card__listdate")
                        if time_tag and time_tag.get("datetime"):
                            try:
                                posted_date = datetime.strptime(
                                    time_tag["datetime"], "%Y-%m-%d"
                                )
                            except (ValueError, TypeError):
                                pass

                        remote = None
                        check_str = f"{title or ''} {loc or ''}".lower()
                        if "remote" in check_str:
                            remote = "remote"
                        elif "hybrid" in check_str:
                            remote = "hybrid"

                        all_results.append(
                            {
                                "source_job_id": job_id,
                                "title": title,
                                "company": company or "LinkedIn",
                                "department": None,
                                "location": loc,
                                "remote": remote,
                                "salary_min": None,
                                "salary_max": None,
                                "description": None,
                                "requirements": None,
                                "nice_to_haves": None,
                                "apply_url": href,
                                "posted_date": posted_date,
                                "company_industry": None,
                                "company_size": None,
                                "source_type": "aggregator",
                            }
                        )
                        parsed_any = True

                    if not parsed_any:
                        break

                    time.sleep(1)  # polite delay between pages

                except requests.RequestException as e:
                    logger.warning(f"LinkedIn request failed for '{term}': {e}")
                    break

        return all_results

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        # _fetch_jobs already returns the standardised format
        return raw_job
