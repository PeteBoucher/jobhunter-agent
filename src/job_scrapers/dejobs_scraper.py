"""DeJobs / JobSyn microsite scraper.

Companies using this platform host career microsites at {slug}.dejobs.org.
Each microsite is backed by a shared Solr search API that filters by the
request's x-origin header.

API:
  GET https://prod-search-api.jobsyn.org/api/v1/solr/search?q=&page={n}
  Header: x-origin: {hostname}

  Returns paginated job listings including title, location, description, and
  a GUID. Apply URL is constructed as https://de.jobsyn.org/{guid}10.

To add a new company: find their .dejobs.org hostname and add a DeJobsCompany
entry to DEFAULT_COMPANIES.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.dejobs")

SEARCH_URL = "https://prod-search-api.jobsyn.org/api/v1/solr/search"
APPLY_URL_TPL = "https://de.jobsyn.org/{guid}10"

DEFAULT_MAX_JOBS = 500


@dataclass
class DeJobsCompany:
    """Configuration for a single .dejobs.org microsite."""

    hostname: str  # e.g. "nttdata.dejobs.org"
    name: str  # display name, e.g. "NTT Data"
    max_jobs: int = field(default=DEFAULT_MAX_JOBS)


DEFAULT_COMPANIES: List[DeJobsCompany] = [
    DeJobsCompany(hostname="nttdata.dejobs.org", name="NTT Data", max_jobs=500),
]


class DeJobsScraper(BaseScraper):
    """Scraper for DeJobs/JobSyn-hosted company career microsites."""

    def __init__(
        self, session: Session, companies: Optional[List[DeJobsCompany]] = None
    ):
        super().__init__(session)
        self.companies = companies or DEFAULT_COMPANIES
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "dejobs"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db_companies = [
            DeJobsCompany(
                hostname=c["hostname"],
                name=c.get("name", c["hostname"]),
                max_jobs=int(c.get("max_jobs", DEFAULT_MAX_JOBS)),
            )
            for c in self._load_db_config()
            if "hostname" in c
        ]
        companies = self.companies + db_companies
        all_raw: List[Dict[str, Any]] = []
        for company in companies:
            listings = self._fetch_company(company)
            all_raw.extend(listings)
            logger.info("Fetched %d jobs from %s", len(listings), company.name)
        return all_raw

    def _fetch_company(self, company: DeJobsCompany) -> List[Dict[str, Any]]:
        listings: List[Dict[str, Any]] = []
        page = 1

        while len(listings) < company.max_jobs:
            try:
                resp = self._http.get(
                    SEARCH_URL,
                    params={"q": "", "page": str(page)},
                    headers={"x-origin": company.hostname},
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("DeJobs fetch error [%s]: %s", company.name, e)
                break

            data = resp.json()
            jobs = data.get("jobs", [])
            if not jobs:
                break

            for job in jobs:
                job["_company"] = company
            listings.extend(jobs)

            pagination = data.get("pagination", {})
            total_pages = pagination.get("total_pages") or 1
            if page >= total_pages:
                break
            page += 1

        return listings[: company.max_jobs]

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        company: DeJobsCompany = raw_job["_company"]
        guid = raw_job.get("guid") or ""

        title = raw_job.get("title_exact") or ""
        company_name = raw_job.get("company_exact") or company.name
        location = raw_job.get("location_exact") or raw_job.get("city_exact") or None

        remote = _infer_remote(raw_job.get("description") or "", title)

        description_raw = raw_job.get("description") or ""
        description = description_raw[:5000] if description_raw else None

        date_str = raw_job.get("date_new") or raw_job.get("date_added") or ""
        posted_date = _parse_date(date_str)

        return {
            "source_job_id": f"{company.hostname}:{guid}",
            "title": title,
            "company": company_name,
            "department": None,
            "location": location,
            "remote": remote,
            "country": None,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": None,
            "nice_to_haves": None,
            "apply_url": APPLY_URL_TPL.format(guid=guid) if guid else None,
            "posted_date": posted_date,
            "company_industry": "Technology",
            "company_size": None,
            "source_type": "company_portal",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _infer_remote(description: str, title: str) -> Optional[str]:
    text = (description + " " + title).lower()
    if "hybrid" in text:
        return "hybrid"
    if "remote" in text:
        return "remote"
    return None


def _parse_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.utcnow()
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except (ValueError, TypeError):
        return datetime.utcnow()


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean
