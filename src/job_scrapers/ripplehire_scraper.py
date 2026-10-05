"""RippleHire ATS scraper.

RippleHire hosts career sites on a per-company subdomain
(`{subdomain}.ripplehire.com/candidate`), gated by an opaque `token` +
`source` query pair rather than a company slug. The candidate-facing SPA
talks to two internal endpoints (neither documented publicly, found via a
headless-browser network capture — an AI-generated first draft guessed
plausible-sounding endpoint names, `getjoblist`/`getjobdetails`, that don't
exist and 404 for every request):

  Listings (POST, form-encoded, XML response):
    {base}/candidatejobsearch
    body: careerSiteUrlParams={"page":N,"search":"*:*","token":...,
                                "source":...,"pagesize":N}
          &lang=en

  Detail (GET, XML response, only worth calling for jobs not already in
  the DB — see WorkdayScraper's max_jobs/description-fetch pattern, which
  this mirrors):
    {base}/candidatejobdetail?token=...&source=...&lang=en&jobSeq={id}

Both endpoints return `application/xml`, not JSON. The detail endpoint also
appends a stray "An unexpected error occurred" string after the closing
`</CandidateJobVO>` tag on every request (observed consistently, cause
unknown — not related to auth or params) — trimmed before parsing.

Confirmed working instance (as of 2026-09):
  UST (usource) — usource.ripplehire.com, token xHQWoFn4C242POo7xMpH,
                   source CAREERSITE (~1180 jobs across 40+ countries)

NOTE: `job-agent scraper add <ripplehire-url>` will re-run the AI generator
and overwrite this file, since ats_detector.py has no RippleHire signature
(same wrong endpoint guesses every time). To add another RippleHire company,
add a ScraperConfig DB row directly (source_name="ripplehire", config
{"subdomain": ..., "token": ..., "company": ...}) or extend
RIPPLEHIRE_INSTANCES below — do not run `scraper add`/`scraper generate`
against a ripplehire.com URL.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from defusedxml import ElementTree
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.ripplehire")

# Throttle between per-job detail fetches to be polite
DETAIL_DELAY = 0.1  # seconds

PAGE_SIZE = 50

# Default cap for instances that don't set their own max_jobs.
DEFAULT_MAX_JOBS = 300

_DETAIL_CLOSE_TAG = "</CandidateJobVO>"


@dataclass
class RippleHireInstance:
    """Configuration for a single RippleHire-hosted careers site."""

    subdomain: str  # e.g. "usource"
    token: str
    company: str
    source: str = "CAREERSITE"
    max_jobs: int = DEFAULT_MAX_JOBS

    @property
    def base_url(self) -> str:
        return f"https://{self.subdomain}.ripplehire.com/candidate"

    @property
    def search_url(self) -> str:
        return f"{self.base_url}/candidatejobsearch"

    @property
    def detail_url(self) -> str:
        return f"{self.base_url}/candidatejobdetail"


# ── Confirmed working instances ────────────────────────────────────────────

RIPPLEHIRE_INSTANCES: List[RippleHireInstance] = [
    RippleHireInstance(
        subdomain="usource",
        token="xHQWoFn4C242POo7xMpH",
        company="UST",
        max_jobs=500,
    ),
]


class RippleHireScraper(BaseScraper):
    """Scraper for RippleHire-hosted career sites.

    Fetches job listings from multiple company instances via the internal
    candidatejobsearch API. For new jobs (not already in the DB), also
    fetches the full description/skills from the detail endpoint.

    source_job_id format: "{subdomain}:{jobSeq}" to avoid cross-company
    collisions.
    """

    def __init__(
        self,
        session: Session,
        instances: Optional[List[RippleHireInstance]] = None,
    ):
        super().__init__(session)
        self.instances = instances or RIPPLEHIRE_INSTANCES
        self._http = requests.Session()
        self._http.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "ripplehire"

    # ── Fetch ────────────────────────────────────────────────────────────

    def _fetch_instance_listings(
        self, instance: RippleHireInstance
    ) -> List[Dict[str, Any]]:
        """Paginate through job listings for a single instance."""
        listings: List[Dict[str, Any]] = []
        page = 0

        while len(listings) < instance.max_jobs:
            params = (
                '{"page":%d,"search":"*:*","token":"%s","source":"%s",'
                '"pagesize":%d}' % (page, instance.token, instance.source, PAGE_SIZE)
            )
            try:
                resp = self._http.post(
                    instance.search_url,
                    data={"careerSiteUrlParams": params, "lang": "en"},
                    timeout=15,
                )
                resp.raise_for_status()
                root = ElementTree.fromstring(resp.text)
            except (requests.RequestException, ElementTree.ParseError) as e:
                logger.warning(
                    "RippleHire search error [%s] at page %d: %s",
                    instance.company,
                    page,
                    e,
                )
                break

            page_jobs = root.findall("./jobVoList/jobVoList")
            if not page_jobs:
                break

            for job_el in page_jobs:
                listings.append({child.tag: child.text for child in job_el})

            total = int((root.findtext("totalJobCount") or "0"))
            page += 1
            if page * PAGE_SIZE >= total:
                break

        logger.info("Fetched %d listings from %s", len(listings), instance.company)
        return listings

    def _fetch_detail(
        self, instance: RippleHireInstance, job_seq: str
    ) -> Optional[Dict[str, Optional[str]]]:
        """Fetch full job description/skills/date from the detail endpoint."""
        try:
            resp = self._http.get(
                instance.detail_url,
                params={
                    "token": instance.token,
                    "source": instance.source,
                    "lang": "en",
                    "jobSeq": job_seq,
                },
                timeout=15,
            )
            resp.raise_for_status()
            text = resp.text
            end = text.find(_DETAIL_CLOSE_TAG)
            if end != -1:
                text = text[: end + len(_DETAIL_CLOSE_TAG)]
            root = ElementTree.fromstring(text)
            job_el = root.find("jobVO")
            if job_el is None:
                return None
            return {child.tag: child.text for child in job_el}
        except (requests.RequestException, ElementTree.ParseError) as e:
            logger.debug(
                "Could not fetch detail for %s job %s: %s",
                instance.company,
                job_seq,
                e,
            )
            return None

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch listings from all instances; hydrate new jobs with details."""
        existing_ids: set = self._load_existing_ids()
        db_instances = [
            RippleHireInstance(
                subdomain=c["subdomain"],
                token=c["token"],
                company=c.get("company", c["subdomain"]),
                source=c.get("source", "CAREERSITE"),
                max_jobs=int(c.get("max_jobs", DEFAULT_MAX_JOBS)),
            )
            for c in self._load_db_config()
            if "subdomain" in c and "token" in c
        ]
        instances = self.instances + db_instances
        all_raw: List[Dict[str, Any]] = []

        for instance in instances:
            try:
                listings = self._fetch_instance_listings(instance)
            except Exception as e:
                logger.warning(
                    "Failed to fetch listings for %s: %s", instance.company, e
                )
                continue

            new_count = 0
            for listing in listings:
                job_seq = listing.get("jobSeq", "")
                source_job_id = f"{instance.subdomain}:{job_seq}"
                listing["_instance"] = instance
                listing["_source_job_id"] = source_job_id
                listing["_detail"] = None

                if source_job_id not in existing_ids and job_seq:
                    listing["_detail"] = self._fetch_detail(instance, job_seq)
                    time.sleep(DETAIL_DELAY)
                    new_count += 1

                all_raw.append(listing)

            logger.info(
                "%s: %d total, %d new", instance.company, len(listings), new_count
            )

        return all_raw

    # ── Parse ────────────────────────────────────────────────────────────

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        instance: RippleHireInstance = raw_job["_instance"]
        detail = raw_job.get("_detail") or {}

        job_seq = raw_job.get("jobSeq", "")
        title = (raw_job.get("jobTitle") or "").strip()
        if not job_seq or not title:
            return {}

        location = (
            detail.get("jobLocation")
            or raw_job.get("locations")
            or raw_job.get("jobLocation")
            or None
        )
        if location:
            location = location.strip() or None
        remote = _parse_remote(location)

        description = _strip_html(detail.get("jobDesc")) or None
        requirements = _split_skills(detail.get("jobSkills"))
        posted_date = _parse_posted_date(detail.get("jobPostingDate"))

        apply_url = (
            f"{instance.base_url}/?token={instance.token}"
            f"&source={instance.source}#detail/job/{job_seq}"
        )

        return {
            "source_job_id": raw_job["_source_job_id"],
            "title": title,
            "company": instance.company,
            "department": raw_job.get("bussinessUnit") or None,
            "location": location,
            "remote": remote,
            "country": None,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": None,
            "posted_date": posted_date,
            "apply_url": apply_url,
            "company_industry": None,
            "company_size": None,
            "source_type": "company_portal",
        }


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_remote(location: Optional[str]) -> Optional[str]:
    if not location:
        return None
    loc = location.lower()
    if "hybrid" in loc:
        return "hybrid"
    if "remote" in loc:
        return "remote"
    return None


def _strip_html(html: Optional[str]) -> Optional[str]:
    if not html:
        return None
    import re

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _split_skills(skills_html: Optional[str]) -> Optional[List[str]]:
    text = _strip_html(skills_html)
    if not text:
        return None
    return [s.strip() for s in text.split(",") if s.strip()]


def _parse_posted_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str.strip(), "%d-%b-%Y")
    except ValueError:
        return None
