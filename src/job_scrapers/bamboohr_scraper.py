"""BambooHR careers scraper.

BambooHR is an ATS used by many mid-size companies.
Each company has its own subdomain: https://{slug}.bamboohr.com/

Discovery is via the public list endpoint (no auth required).
Descriptions are fetched per-job from the detail endpoint for new listings only.

locationType values: "0" = on-site, "1" = remote, "2" = hybrid
"""

import html as html_module
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

# Map of slug → display company name. Falls back to slug.title().
COMPANY_NAMES: Dict[str, str] = {
    "semble": "Semble",
}

_LOCATION_TYPE_MAP: Dict[str, Optional[str]] = {
    "0": None,
    "1": "remote",
    "2": "hybrid",
}

_COUNTRY_MAP: Dict[str, str] = {
    "united kingdom": "gb",
    "united states": "us",
    "united states of america": "us",
    "canada": "ca",
    "australia": "au",
    "germany": "de",
    "france": "fr",
    "netherlands": "nl",
    "ireland": "ie",
    "spain": "es",
    "italy": "it",
    "poland": "pl",
    "sweden": "se",
    "norway": "no",
    "denmark": "dk",
    "portugal": "pt",
    "belgium": "be",
    "switzerland": "ch",
    "romania": "ro",
    "india": "in",
}

DEFAULT_COMPANY_SLUGS = ["semble"]


class BambooHRScraper(BaseScraper):
    """Scraper for BambooHR-hosted job boards.

    Fetches all open listings from each configured company's /careers/list
    endpoint, then fetches /careers/{id}/detail for new jobs to get
    descriptions. Existing jobs are included in results (no detail fetch)
    so BaseScraper can refresh their scraped_at timestamp.
    """

    def __init__(self, session: Session, company_slugs: Optional[List[str]] = None):
        super().__init__(session)
        self._http = requests.Session()
        self.company_slugs = company_slugs or DEFAULT_COMPANY_SLUGS

    def _get_source_name(self) -> str:
        return "bamboohr"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        existing = self._load_existing_ids()
        all_jobs: List[Dict[str, Any]] = []

        for slug in self.company_slugs:
            try:
                resp = self._http.get(
                    f"https://{slug}.bamboohr.com/careers/list",
                    timeout=15,
                )
                resp.raise_for_status()
                jobs = resp.json().get("result", [])
                self.logger.info("bamboohr slug=%s listed=%d", slug, len(jobs))

                for job in jobs:
                    title = (job.get("jobOpeningName") or "").strip()
                    if not title or "talent pool" in title.lower():
                        continue

                    source_job_id = f"{slug}-{job['id']}"
                    job["_slug"] = slug
                    job["_source_job_id"] = source_job_id

                    if source_job_id not in existing:
                        job["_detail"] = self._fetch_detail(slug, job["id"])
                        time.sleep(0.1)
                    else:
                        job["_detail"] = {}

                    all_jobs.append(job)

            except Exception as exc:
                self.logger.warning("bamboohr slug=%s error=%s", slug, exc)

        return all_jobs

    def _fetch_detail(self, slug: str, job_id: str) -> Dict[str, Any]:
        try:
            resp = self._http.get(
                f"https://{slug}.bamboohr.com/careers/{job_id}/detail",
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("result", {}).get("jobOpening", {})
        except Exception as exc:
            self.logger.warning(
                "bamboohr slug=%s job_id=%s detail_error=%s", slug, job_id, exc
            )
        return {}

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        slug = raw_job["_slug"]
        detail = raw_job.get("_detail") or {}

        title = (raw_job.get("jobOpeningName") or "").strip()
        department = raw_job.get("departmentLabel")

        list_loc = raw_job.get("location") or {}
        detail_loc = detail.get("location") or {}
        ats_loc = detail.get("atsLocation") or {}

        city = list_loc.get("city") or ats_loc.get("city")
        state = list_loc.get("state") or ats_loc.get("state")
        country_name = (
            detail_loc.get("addressCountry") or ats_loc.get("country") or ""
        ).lower()
        country = _COUNTRY_MAP.get(country_name)

        location_parts = [p for p in [city, state] if p]
        location = ", ".join(location_parts) if location_parts else None

        remote = _LOCATION_TYPE_MAP.get(str(raw_job.get("locationType") or ""))

        description: Optional[str] = None
        desc_html = detail.get("description") or ""
        if desc_html:
            soup = BeautifulSoup(html_module.unescape(desc_html), "html.parser")
            description = soup.get_text(separator="\n").strip() or None

        date_str = detail.get("datePosted")
        try:
            posted_date = (
                datetime.strptime(date_str, "%Y-%m-%d")
                if date_str
                else datetime.utcnow()
            )
        except (ValueError, TypeError):
            posted_date = datetime.utcnow()

        return {
            "source_job_id": raw_job["_source_job_id"],
            "title": title or None,
            "company": COMPANY_NAMES.get(slug, slug.title()),
            "department": department,
            "location": location,
            "remote": remote,
            "country": country,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": f"https://{slug}.bamboohr.com/careers/{raw_job['id']}",
            "posted_date": posted_date,
            "company_industry": None,
            "company_size": None,
            "source_type": "company_portal",
        }
