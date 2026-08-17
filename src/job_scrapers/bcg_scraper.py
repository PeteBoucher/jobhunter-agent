"""BCG (Boston Consulting Group) careers scraper.

BCG uses Phenom People, a fully client-side-rendered job platform with no
accessible JSON API.  We discover live jobs via the two XML sitemaps, then
fetch each new job's HTML page to extract server-rendered OG meta tags
(title, location, department).

All departments are stored so that every job ID is recorded in the DB after
the first run.  This prevents non-tech jobs from being re-fetched on every
subsequent run (they would otherwise appear "new" forever since only stored
IDs are skipped).  The matching engine handles relevance filtering.

Perf profile:
  First run  — up to ~900 HTTP requests (one per job page, ~200ms each).
  Later runs — only new postings since the last run (typically <20/day).
"""

import re
import time
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

_SITEMAPS = [
    "https://careers.bcg.com/global/en/sitemap1.xml",
    "https://careers.bcg.com/global/en/sitemap2.xml",
]
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class BCGScraper(BaseScraper):
    """Scraper for BCG Technology and Engineering careers (Phenom People)."""

    def __init__(self, session: Session):
        super().__init__(session)
        self._http = requests.Session()
        self._http.headers.update(_HEADERS)

    def _get_source_name(self) -> str:
        return "bcg"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        sitemap_jobs = self._jobs_from_sitemaps()
        self.logger.info("bcg sitemap_jobs=%d", len(sitemap_jobs))

        existing = self._load_existing_ids()
        new_jobs = [(jid, url) for jid, url in sitemap_jobs if jid not in existing]
        self.logger.info("bcg new_jobs=%d", len(new_jobs))

        results: List[Dict[str, Any]] = []
        for job_id, url in new_jobs:
            try:
                job = self._fetch_job_meta(job_id, url)
                if job:
                    results.append(job)
            except Exception as exc:
                self.logger.warning("bcg job_id=%s fetch_error=%s", job_id, exc)
            # Polite crawl delay — avoids triggering rate-limits on a large first run
            time.sleep(0.15)

        self.logger.info("bcg fetched_jobs=%d", len(results))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _jobs_from_sitemaps(self) -> List[tuple]:
        """Return deduplicated (job_id, url) pairs from all BCG sitemaps."""
        pairs: List[tuple] = []
        seen: set = set()
        for sitemap_url in _SITEMAPS:
            resp = self._http.get(sitemap_url, timeout=15)
            resp.raise_for_status()
            for url in re.findall(r"<loc>(.*?)</loc>", resp.text):
                m = re.search(r"/job/(\d+)/", url)
                if m and m.group(1) not in seen:
                    seen.add(m.group(1))
                    pairs.append((m.group(1), url))
        return pairs

    def _fetch_job_meta(self, job_id: str, url: str) -> Optional[Dict[str, Any]]:
        """Fetch one job page and extract structured data from OG meta tags.

        OG title format:
          "{title} in {location} | {department} at BCG"
        OG description format:
          "Apply for {title} job with BCG in {location}. {department} at BCG"
        """
        resp = self._http.get(url, timeout=15)
        if resp.status_code != 200:
            return None

        def _og(prop: str) -> str:
            m = re.search(
                rf'<meta\s+property="og:{prop}"\s+content="([^"]+)"',
                resp.text,
            )
            return m.group(1) if m else ""

        og_title = _og("title")
        og_url = _og("url") or url

        title = og_title
        location: Optional[str] = None
        department: Optional[str] = None

        # "Senior AI Architect in London, UK | Technology and Engineering at BCG"
        if " | " in og_title:
            left, right = og_title.rsplit(" | ", 1)
            department = right.replace(" at BCG", "").strip()

            # "Senior AI Architect in London, UK" — split on last " in "
            if " in " in left:
                idx = left.rfind(" in ")
                title = left[:idx].strip()
                location = left[idx + 4 :].strip()
            else:
                title = left.strip()

        return {
            "source_job_id": job_id,
            "title": title or None,
            "company": "BCG",
            "department": department,
            "location": location,
            "remote": None,
            "country": None,
            "salary_min": None,
            "salary_max": None,
            "description": None,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": og_url,
            "posted_date": None,
            "company_industry": "Management Consulting",
            "company_size": "Large",
            "source_type": "company_portal",
        }

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        return raw_job
