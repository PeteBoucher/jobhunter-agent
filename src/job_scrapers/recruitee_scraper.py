"""Recruitee job board scraper.

Recruitee is an ATS whose "Career Site Builder" product renders job
listings directly into a company's own page — either a {company}.recruitee.com
subdomain or a custom domain (e.g. meet.zoi.tech). Either way it exposes a
public JSON API, unauthenticated, at /api/offers/.

Discovered via meet.zoi.tech: its homepage lists 11 open positions with
/o/{slug} links and mentions "recruitee" ~90 times in the page source
(recruiteecdn.com asset host), but the AI scraper generator couldn't find
a live endpoint via static probing or headless network capture — the
homepage IS the job listing (no separate XHR call fires; it's server-side
rendered), so the generator's HTML-sample fallback should have found it,
but the class-name heuristics didn't match Recruitee's markup. The actual
API only turned up by testing the well-known Recruitee endpoint pattern
directly against the custom domain.

API endpoint:
  GET https://{career_site}/api/offers/
  Returns {"offers": [...]}, no pagination — all published offers at once.

To add a new company: find their Recruitee career URL (look for
'recruiteecdn.com' or "recruitee" in page source), verify the
/api/offers/ endpoint works, then add a RecruiteeBoard entry to
DEFAULT_BOARDS below.

Most of the companies below were sourced from Recruitee's own customer
list (recruitee.com/customer-success-stories) and confirmed live by
guessing the default {slug}.recruitee.com subdomain — the platform default
before a company points a custom domain at it. Several customer-list
companies (Ströer X, SPECTO, Sword Group, Equalture, Incentro, Teamleader,
Origin Materials, Heras, Mopinion, Makerstreet, Slingshot Group) did NOT
resolve on the guessable subdomain pattern; they likely use a custom
domain that would need individual lookup to find, same as bunq/Zoi.

bunq is a special case: its public careers page (careers.bunq.com) is a
custom Framer-built UI with zero Recruitee branding or fingerprints in the
page source, so ats_detector.py can't and won't ever detect it — but
bunq.recruitee.com serves the identical 10 jobs (same titles, same
careers_url pointing back to careers.bunq.com), confirming the Framer
front-end is just a skin over the same Recruitee backend. Listed here
instead of a hand-rolled HTML scraper for that reason: it's simpler and
gives richer structured data (full city/region/country, reliable
descriptions) than scraping the custom front-end ever could.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.recruitee")


@dataclass
class RecruiteeBoard:
    """Configuration for a single Recruitee-hosted career site."""

    company: str  # display name, e.g. "Zoi"
    career_url: str  # base URL of the Recruitee career site


DEFAULT_BOARDS: List[RecruiteeBoard] = [
    RecruiteeBoard(
        company="Zoi",
        career_url="https://meet.zoi.tech",
    ),
    RecruiteeBoard(
        company="bunq",
        career_url="https://bunq.recruitee.com",
    ),
    RecruiteeBoard(
        company="Keolis",
        career_url="https://keolis.recruitee.com",
    ),
    RecruiteeBoard(
        company="Pret A Manger",
        career_url="https://pretamanger.recruitee.com",
    ),
    RecruiteeBoard(
        company="Livestorm",
        career_url="https://livestorm.recruitee.com",
    ),
    RecruiteeBoard(
        company="Van Cranenbroek",
        career_url="https://vancranenbroek.recruitee.com",
    ),
    RecruiteeBoard(
        company="Woonzorg Flevoland",
        career_url="https://woonzorgflevoland.recruitee.com",
    ),
    RecruiteeBoard(
        company="Betty Blocks",
        career_url="https://bettyblocks.recruitee.com",
    ),
    RecruiteeBoard(
        company="CM.com",
        career_url="https://cmcom.recruitee.com",
    ),
    RecruiteeBoard(
        company="Greenpeace CEE",
        career_url="https://greenpeacecee.recruitee.com",
    ),
    RecruiteeBoard(
        company="Sircle Collection",
        career_url="https://sirclecollection.recruitee.com",
    ),
    RecruiteeBoard(
        company="Solutions 4 Delivery",
        career_url="https://solutions4delivery.recruitee.com",
    ),
    RecruiteeBoard(
        company="Trusted Shops",
        career_url="https://trustedshops.recruitee.com",
    ),
]


class RecruiteeScraper(BaseScraper):
    """Scraper for Recruitee-hosted career sites.

    Uses the public /api/offers/ JSON endpoint, which returns full offer
    detail (description, location, remote/hybrid flags, salary) in one
    unauthenticated request — no per-job detail fetch needed.
    """

    def __init__(self, session: Session, boards: Optional[List[RecruiteeBoard]] = None):
        super().__init__(session)
        self.boards = boards or DEFAULT_BOARDS
        self._http = requests.Session()
        self._http.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )

    def _get_source_name(self) -> str:
        return "recruitee"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        db_boards = [
            RecruiteeBoard(
                company=c.get("company", c.get("career_url", "")),
                career_url=c["career_url"],
            )
            for c in self._load_db_config()
            if "career_url" in c
        ]
        boards = self.boards + db_boards
        all_raw: List[Dict[str, Any]] = []

        for board in boards:
            url = f"{board.career_url.rstrip('/')}/api/offers/"
            try:
                resp = self._http.get(url, timeout=15)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Recruitee fetch error [%s]: %s", board.company, e)
                continue

            data = resp.json()
            offers = data.get("offers", [])
            for offer in offers:
                offer["_board"] = board
            all_raw.extend(offers)
            logger.info("Fetched %d jobs from %s", len(offers), board.company)

        return all_raw

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        board: RecruiteeBoard = raw_job["_board"]

        job_id = str(raw_job.get("id") or raw_job.get("slug") or "")
        title = raw_job.get("title") or ""

        description_html = raw_job.get("description") or ""
        description = _strip_html(description_html)[:5000] if description_html else None

        requirements_html = raw_job.get("requirements") or ""
        requirements = (
            _strip_html(requirements_html)[:2000] if requirements_html else None
        )

        location = raw_job.get("city") or raw_job.get("location")
        country_code = (raw_job.get("country_code") or "").lower() or None

        remote = _parse_remote(raw_job)

        salary = raw_job.get("salary") or {}
        period = salary.get("period")
        hours_per_week = raw_job.get("max_hours") or raw_job.get("min_hours")
        salary_min = _annual_salary(salary.get("min"), period, hours_per_week)
        salary_max = _annual_salary(salary.get("max"), period, hours_per_week)

        posted_date = _parse_date(raw_job.get("published_at"))

        apply_url = raw_job.get("careers_url") or board.career_url

        return {
            "source_job_id": f"{_slug(board.company)}:{job_id}",
            "title": title,
            "company": board.company,
            "department": raw_job.get("department"),
            "location": location,
            "remote": remote,
            "country": country_code,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "source_type": "company_portal",
        }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_remote(offer: Dict[str, Any]) -> Optional[str]:
    """Map Recruitee's remote/hybrid/on_site booleans to the canonical enum."""
    if offer.get("remote"):
        return "remote"
    if offer.get("hybrid"):
        return "hybrid"
    if offer.get("on_site"):
        return "onsite"
    return None


_SALARY_PERIOD_MULTIPLIERS = {"year": 1, "month": 12, "week": 52, "day": 260}


def _annual_salary(
    value: Any, period: Optional[str], hours_per_week: Any
) -> Optional[float]:
    """Convert a Recruitee salary figure to an approximate annual amount.

    salary.min/max come back as numeric strings (e.g. "2500", "3592.96"),
    not numbers — found live on Van Cranenbroek/Woonzorg Flevoland/Keolis
    (Zoi's own postings never set a salary, so this went unnoticed until
    scraping companies that do). salary.period also varies ("month" for
    most, "hour" for Keolis's transport roles) — every other salary_min/
    salary_max in this codebase is an implicitly annual figure (see
    adzuna_scraper.py, whose API always returns annual), so storing a raw
    monthly/hourly number as-is would silently corrupt salary matching.
    Hourly rates are annualized using the posting's own hours-per-week
    when available, falling back to a 40-hour full-time assumption.
    """
    if value in (None, ""):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None

    period = (period or "year").lower()
    if period == "hour":
        try:
            hours = float(hours_per_week) if hours_per_week else 40.0
        except (TypeError, ValueError):
            hours = 40.0
        return amount * hours * 52
    return amount * _SALARY_PERIOD_MULTIPLIERS.get(period, 1)


def _parse_date(date_str: Optional[str]) -> datetime:
    """Parse Recruitee's "YYYY-MM-DD HH:MM:SS UTC" timestamp format."""
    if not date_str:
        return datetime.utcnow()
    try:
        return datetime.strptime(date_str.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return datetime.utcnow()


def _strip_html(html: str) -> str:
    clean = re.sub(r"<[^>]+>", " ", html)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
