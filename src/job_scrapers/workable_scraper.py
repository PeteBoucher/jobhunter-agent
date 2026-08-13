"""Workable ATS scraper.

Workable is an ATS used by many companies. Each company has a public career
page at https://apply.workable.com/{slug}/ and an unauthenticated API:

  List:   POST https://apply.workable.com/api/v3/accounts/{slug}/jobs
          Body: {"query":"","location":[],"department":[],"worktype":[],"remote":[]}
          Paginates via "nextPage" token in the response.

  Detail: GET  https://apply.workable.com/api/v2/accounts/{slug}/jobs/{shortcode}
          Returns description (HTML) and requirements (HTML).

To add a new company: find their Workable URL slug (the part after
apply.workable.com/) and add a WorkableCompany entry to DEFAULT_COMPANIES.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.workable")

LIST_URL = "https://apply.workable.com/api/v3/accounts/{slug}/jobs"
DETAIL_URL = "https://apply.workable.com/api/v2/accounts/{slug}/jobs/{shortcode}"
APPLY_URL = "https://apply.workable.com/{slug}/j/{shortcode}/"


@dataclass
class WorkableCompany:
    """Configuration for a single Workable-hosted career page."""

    slug: str  # URL slug, e.g. "360dialog-gmbh"
    name: str  # Display name, e.g. "360dialog"


DEFAULT_COMPANIES: List[WorkableCompany] = [
    WorkableCompany(slug="360dialog-gmbh", name="360dialog"),
]


class WorkableScraper(BaseScraper):
    """Scraper for Workable-hosted career pages."""

    def __init__(
        self, session: Session, companies: Optional[List[WorkableCompany]] = None
    ):
        super().__init__(session)
        self.companies = companies or DEFAULT_COMPANIES
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "workable"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        all_raw: List[Dict[str, Any]] = []

        for company in self.companies:
            listings = self._fetch_company(company)
            all_raw.extend(listings)
            logger.info("Fetched %d jobs from %s", len(listings), company.name)

        return all_raw

    def _fetch_company(self, company: WorkableCompany) -> List[Dict[str, Any]]:
        url = LIST_URL.format(slug=company.slug)
        payload: Dict[str, Any] = {
            "query": "",
            "location": [],
            "department": [],
            "worktype": [],
            "remote": [],
        }
        listings: List[Dict[str, Any]] = []

        while True:
            try:
                resp = self._http.post(url, json=payload, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Workable fetch error [%s]: %s", company.name, e)
                break

            data = resp.json()
            for job in data.get("results", []):
                job["_company"] = company
                listings.append(job)

            next_page = data.get("nextPage")
            if not next_page:
                break
            payload["token"] = next_page

        return listings

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        company: WorkableCompany = raw_job["_company"]
        shortcode = raw_job.get("shortcode", "")

        location_data = raw_job.get("location") or {}
        country_code = (location_data.get("countryCode") or "").lower() or None
        city = location_data.get("city") or None

        remote_flag = raw_job.get("remote")
        remote = "remote" if remote_flag else None

        departments = raw_job.get("department") or []
        department = departments[0] if departments else None

        date_str = raw_job.get("published") or ""
        posted_date = _parse_date(date_str)

        description, requirements = self._fetch_detail(company.slug, shortcode)

        return {
            "source_job_id": f"{company.slug}:{shortcode}",
            "title": raw_job.get("title") or "",
            "company": company.name,
            "department": department,
            "location": city,
            "remote": remote,
            "country": country_code,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": None,
            "apply_url": APPLY_URL.format(slug=company.slug, shortcode=shortcode),
            "posted_date": posted_date,
            "company_industry": "Technology",
            "company_size": None,
            "source_type": "company_portal",
        }

    def _fetch_detail(self, slug: str, shortcode: str) -> tuple:
        url = DETAIL_URL.format(slug=slug, shortcode=shortcode)
        try:
            resp = self._http.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.warning(
                "Workable detail fetch error [%s/%s]: %s", slug, shortcode, e
            )
            return None, None

        data = resp.json()
        desc_html = data.get("description") or ""
        req_html = data.get("requirements") or ""

        description = _strip_html(desc_html)[:5000] if desc_html else None
        requirements = _strip_html(req_html)[:2000] if req_html else None
        return description, requirements


# ── Helpers ───────────────────────────────────────────────────────────────────


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.utcnow()
    try:
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return datetime.utcnow()
