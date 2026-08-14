"""SmartRecruiters job board scraper.

SmartRecruiters provides a public REST API for fetching job postings.

List endpoint (paginated):
  GET https://api.smartrecruiters.com/v1/companies/{company_id}/postings
      ?limit=100&offset=0

Detail endpoint (full description + applyUrl):
  GET https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{posting_id}

No authentication required for public postings.

locationType: remote/hybrid booleans on the location object.
jobAd.sections: jobDescription, qualifications, additionalInformation (HTML).
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

PAGE_SIZE = 100
MAX_JOBS_PER_COMPANY = 300

SR_API_BASE = "https://api.smartrecruiters.com/v1/companies"

# company_id → display name (SmartRecruiters company IDs are case-sensitive)
DEFAULT_COMPANIES: Dict[str, str] = {
    "Bet3651": "Bet365",
    "Playtech": "Playtech",
    "Evolution": "Evolution",
    "sportradar": "Sportradar",
    "EPAM": "EPAM Systems",
    "Ciklum": "Ciklum",
}


class SmartRecruitersScraper(BaseScraper):
    """Scraper for SmartRecruiters-hosted job boards.

    Fetches job listings from multiple companies. For new jobs, fetches
    the detail endpoint to get full description and direct apply URL.
    """

    def __init__(
        self,
        session: Session,
        companies: Optional[Dict[str, str]] = None,
    ):
        super().__init__(session)
        self._http = requests.Session()
        self._http.headers.update({"Accept": "application/json"})
        self.companies = companies if companies is not None else DEFAULT_COMPANIES

    def _get_source_name(self) -> str:
        return "smartrecruiters"

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _fetch_company_listings(self, company_id: str) -> List[Dict[str, Any]]:
        listings: List[Dict[str, Any]] = []
        offset = 0

        while len(listings) < MAX_JOBS_PER_COMPANY:
            try:
                resp = self._http.get(
                    f"{SR_API_BASE}/{company_id}/postings",
                    params={"limit": PAGE_SIZE, "offset": offset},
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.logger.warning(
                    "smartrecruiters company=%s offset=%d error=%s",
                    company_id,
                    offset,
                    exc,
                )
                break

            data = resp.json()
            page = data.get("content", [])
            if not page:
                break

            for job in page:
                job["_company_id"] = company_id

            listings.extend(page)
            total = data.get("totalFound", 0)
            offset += PAGE_SIZE
            if offset >= total:
                break

        self.logger.info(
            "smartrecruiters company=%s listed=%d", company_id, len(listings)
        )
        return listings

    def _fetch_detail(self, company_id: str, posting_id: str) -> Dict[str, Any]:
        try:
            resp = self._http.get(
                f"{SR_API_BASE}/{company_id}/postings/{posting_id}",
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            self.logger.warning(
                "smartrecruiters company=%s posting=%s detail_error=%s",
                company_id,
                posting_id,
                exc,
            )
        return {}

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        existing = self._load_existing_ids()
        db_companies = {
            c["company_id"]: c.get("display_name", c["company_id"])
            for c in self._load_db_config()
            if "company_id" in c
        }
        # Merge onto self.companies so _parse_job can look up display names
        self.companies = {**self.companies, **db_companies}
        all_jobs: List[Dict[str, Any]] = []

        for company_id in self.companies:
            try:
                listings = self._fetch_company_listings(company_id)
            except Exception as exc:
                self.logger.warning(
                    "smartrecruiters company=%s fetch_error=%s", company_id, exc
                )
                continue

            for listing in listings:
                source_job_id = f"{company_id}:{listing['id']}"
                listing["_source_job_id"] = source_job_id

                if source_job_id not in existing:
                    listing["_detail"] = self._fetch_detail(company_id, listing["id"])
                    time.sleep(0.1)
                else:
                    listing["_detail"] = {}

                all_jobs.append(listing)

        return all_jobs

    # ── Parse ─────────────────────────────────────────────────────────────────

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        company_id: str = raw_job["_company_id"]
        detail: Dict[str, Any] = raw_job.get("_detail") or {}

        title = (raw_job.get("name") or "").strip()
        company = self.companies.get(company_id, company_id)

        loc = raw_job.get("location") or {}
        city = loc.get("city")
        country = loc.get("country")  # 2-char ISO code
        location_parts = [p for p in [city] if p]
        location = location_parts[0] if location_parts else None

        remote: Optional[str] = None
        if loc.get("remote"):
            remote = "remote"
        elif loc.get("hybrid"):
            remote = "hybrid"

        dept_obj = raw_job.get("department") or {}
        department = dept_obj.get("label")

        # Description from detail endpoint
        description: Optional[str] = None
        requirements: Optional[str] = None
        if detail:
            sections = (detail.get("jobAd") or {}).get("sections") or {}
            desc_html = (sections.get("jobDescription") or {}).get("text") or ""
            qual_html = (sections.get("qualifications") or {}).get("text") or ""
            description = _html_to_text(desc_html) or None
            requirements = _html_to_text(qual_html) or None

        released = raw_job.get("releasedDate") or ""
        try:
            posted_date = datetime.fromisoformat(released.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            posted_date = datetime.utcnow()

        apply_url = (
            detail.get("applyUrl")
            or detail.get("postingUrl")
            or raw_job.get("ref")
            or ""
        )

        return {
            "source_job_id": raw_job["_source_job_id"],
            "title": title or None,
            "company": company,
            "department": department,
            "location": location,
            "remote": remote,
            "country": country,
            "salary_min": None,
            "salary_max": None,
            "description": description[:5000] if description else None,
            "requirements": requirements[:2000] if requirements else None,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "company_industry": "iGaming",
            "company_size": None,
            "source_type": "company_portal",
        }


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n").strip()
