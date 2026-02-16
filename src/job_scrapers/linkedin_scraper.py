"""LinkedIn jobs scraper.

This implementation uses LinkedIn's guest jobs endpoint which returns HTML
fragments for job postings. Many requests may be blocked or rate-limited by
LinkedIn; this scraper is conservative and will return an empty list if the
endpoint is inaccessible. For reliable scraping consider using official APIs
or an authenticated/browser-driven approach (Playwright/Selenium) with
respect for terms-of-service.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn jobs (guest endpoint).

    Notes:
    - Uses `jobs-guest/jobs/api/seeMoreJobPostings/search` which often returns
      an HTML fragment of job cards. This may stop working at any time.
    - This scraper is implemented defensively and returns an empty list when
      blocked; consider adding an authenticated/browser option when needed.
    """

    LINKEDIN_SEARCH_API = (
        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    )

    def __init__(self, session: Session):
        super().__init__(session)

    def _get_source_name(self) -> str:
        return "linkedin"

    def _fetch_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 0,
        page_size: int = 25,
        max_pages: int = 2,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        params = {
            "keywords": keywords or "",
            "location": location or "",
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        results: List[Dict[str, Any]] = []

        # The guest endpoint uses a start offset (start=0,25,50,...)
        start = page * page_size

        for p in range(max_pages):
            try:
                params["start"] = str(start + p * page_size)
                resp = requests.get(
                    self.LINKEDIN_SEARCH_API, params=params, headers=headers, timeout=10
                )
                if resp.status_code != 200:
                    # Blocked or changed API
                    return []

                # The endpoint returns an HTML fragment containing job cards
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")

                # Try to locate job card list items
                cards = soup.find_all(
                    lambda tag: tag.name in ("li", "div")
                    and tag.get("data-id")
                    or tag.find("a", href=True)
                )

                parsed_any = False
                for card in cards:
                    # Find job link (href contains '/jobs/view/')
                    link = card.find("a", href=True)
                    href = link["href"] if link else None
                    if not href:
                        continue

                    # Heuristic: LinkedIn job view URLs contain '/jobs/view/'
                    if "/jobs/view/" not in href and "/jobs/" not in href:
                        continue

                    title = (
                        (card.find("h3") or card.find("a")).get_text(strip=True)
                        if (card.find("h3") or card.find("a"))
                        else None
                    )
                    company_tag = card.find(
                        class_="result-card__subtitle"
                    ) or card.find(class_="job-result-card__subtitle")
                    company = company_tag.get_text(strip=True) if company_tag else None
                    location_tag = card.find(
                        class_="job-result-card__location"
                    ) or card.find(class_="result-card__location")
                    location = (
                        location_tag.get_text(strip=True) if location_tag else None
                    )

                    posted_date = datetime.utcnow()

                    results.append(
                        {
                            "source_job_id": href.split("/")[-1] if href else href,
                            "title": title,
                            "company": company or "LinkedIn",
                            "department": None,
                            "location": location,
                            "remote": None,
                            "salary_min": None,
                            "salary_max": None,
                            "description": None,
                            "requirements": None,
                            "nice_to_haves": None,
                            "apply_url": href,
                            "posted_date": posted_date,
                            "company_industry": None,
                            "company_size": None,
                            "source_type": "company_portal",
                        }
                    )
                    parsed_any = True

                # Stop if no cards parsed on this page
                if not parsed_any:
                    break

            except Exception:
                # If anything goes wrong assume blocked/changed endpoint
                return []

        return results

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        # LinkedIn guest endpoint returns enough fields already in our fetch
        return raw_job
