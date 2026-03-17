"""Base scraper abstract class for all job scrapers."""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.models import Job, ScraperMetric, UserPreferences

# Configure module logger
logger = logging.getLogger("jobhunter.scrapers")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class BaseScraper(ABC):
    """Abstract base class for all job scrapers.

    Defines the interface that all job scrapers must implement.
    """

    def __init__(self, session: Session):
        """Initialize scraper with database session.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.source_name = self._get_source_name()
        # Set by scrape() after _fetch_jobs() succeeds; 0 means the source
        # returned nothing (API down, auth failure, HTML changed, etc.)
        self.last_raw_count: int = 0

    @abstractmethod
    def _get_source_name(self) -> str:
        """Get the name of the job source.

        Returns:
            Name of the source (e.g., 'github', 'microsoft')
        """
        pass

    @abstractmethod
    def _fetch_jobs(self, **kwargs) -> List[dict]:
        """Fetch raw job data from the source.

        This method should be implemented by subclasses to handle
        the actual scraping/API calls.

        Args:
            **kwargs: Source-specific parameters

        Returns:
            List of dictionaries containing raw job data
        """
        pass

    @abstractmethod
    def _parse_job(self, raw_job: dict) -> dict:
        """Parse raw job data into standardized format.

        Args:
            raw_job: Raw job data from the source

        Returns:
            Parsed job data with standardized fields
        """
        pass

    def scrape(self, **kwargs) -> List[Job]:
        """Main scraping method with retry/backoff for transient fetch errors.

        Fetches jobs from the source, parses them, and stores in database.

        Supports optional kwargs:
          - max_retries: int = number of fetch retries (default 3)
          - backoff_factor: float = base seconds for exponential backoff (default 1.0)

        Args:
            **kwargs: Source-specific parameters

        Returns:
            List of Job objects that were scraped
        """
        max_retries = int(kwargs.pop("max_retries", 3))
        backoff = float(kwargs.pop("backoff_factor", 1.0))

        try:
            # Retry _fetch_jobs on transient errors
            last_exc: Optional[BaseException] = None
            raw_jobs: Optional[List[Any]] = None
            for attempt in range(max_retries):
                try:
                    raw_jobs = self._fetch_jobs(**kwargs)
                    self.last_raw_count = len(raw_jobs)
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        sleep_time = backoff * (2**attempt)
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise

            if raw_jobs is None:
                raise RuntimeError(
                    f"Failed to fetch jobs from {self.source_name}: {last_exc}"
                )

            # Release the DB connection back to the pool before making further
            # queries. _fetch_jobs() can run for a long time (e.g. LinkedIn with
            # many HTTP requests + sleep delays), leaving the connection idle long
            # enough for Neon to close the SSL link. invalidate() drops the
            # connection without attempting a rollback (session.close() tries to
            # rollback, which itself raises if the SSL link is already dead).
            # pool_pre_ping will then open a fresh connection on the next checkout.
            self.session.invalidate()

            # Load all existing source_job_ids for this source in one query
            existing_ids: set = self._load_existing_ids()

            jobs: List[Job] = []
            parse_errors = 0

            for raw_job in raw_jobs:
                try:
                    parsed_data = self._parse_job(raw_job)
                    if parsed_data.get("source_job_id") in existing_ids:
                        continue
                    jobs.append(self._create_job_object(parsed_data))
                except Exception as e:
                    logger.exception(f"Error parsing job from {self.source_name}: {e}")
                    parse_errors += 1
                    continue

            # Save all new jobs in a single commit
            if jobs:
                self.session.add_all(jobs)
                self.session.commit()

            # Record a single summary metric for the run
            try:
                self._record_metric(
                    "jobs_added",
                    len(jobs),
                    f"raw={len(raw_jobs)} errors={parse_errors}",
                )
            except Exception:
                logger.debug("Failed to record jobs_added metric")

            return jobs

        except Exception as e:
            self.session.rollback()
            raise RuntimeError(f"Error scraping {self.source_name}: {e}") from e

    def _record_metric(
        self, action: str, value: int = 1, details: Optional[str] = None
    ) -> None:
        """Helper to persist a scraper metric row.

        This uses a short-lived session commit to ensure metrics are recorded
        even if the main scraping transaction rolls back.
        """
        try:
            metric = ScraperMetric(
                source=self.source_name,
                action=action,
                value=value,
                details=details,
            )
            self.session.add(metric)
            self.session.commit()
        except Exception:
            # If recording fails, try to rollback the metric insert
            # to keep the session stable
            try:
                self.session.rollback()
            except Exception:
                pass

    def _search_terms_from_prefs(
        self, fallback: Optional[List[str]] = None
    ) -> List[str]:
        """Return deduplicated search terms derived from all users' target_titles.

        Falls back to *fallback* (or a minimal generic list) when no preferences
        exist yet — e.g. before the first user signs up.
        """
        rows = self.session.query(UserPreferences.target_titles).all()
        terms: List[str] = []
        seen: set = set()
        for (titles,) in rows:
            if not titles:
                continue
            for t in titles:
                key = t.lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    terms.append(t.strip())
        if terms:
            logger.debug("search_terms_from_prefs source=db count=%d", len(terms))
            return terms
        default = fallback or [
            "product manager",
            "software engineer",
            "project manager",
        ]
        logger.debug("search_terms_from_prefs source=fallback count=%d", len(default))
        return default

    def _countries_from_prefs(self, fallback: Optional[List[str]] = None) -> List[str]:
        """Return deduplicated ISO2 country codes from all users' preferred_countries.

        Falls back to *fallback* (or ["gb"]) when no preferences exist yet.
        """
        rows = self.session.query(UserPreferences.preferred_countries).all()
        codes: List[str] = []
        seen: set = set()
        for (countries,) in rows:
            if not countries:
                continue
            for code in countries:
                c = code.lower().strip()
                if c and c not in seen:
                    seen.add(c)
                    codes.append(c)
        if codes:
            logger.debug("countries_from_prefs source=db count=%d", len(codes))
            return codes
        default = fallback or ["gb"]
        logger.debug("countries_from_prefs source=fallback count=%d", len(default))
        return default

    def _load_existing_ids(self) -> set:
        """Load all known source_job_ids for this source in one query."""
        rows = (
            self.session.query(Job.source_job_id)
            .filter(Job.source == self.source_name)
            .all()
        )
        return {row[0] for row in rows}

    def _create_job_object(self, parsed_data: dict) -> Job:
        """Create a Job object from parsed data.

        Args:
            parsed_data: Parsed job data

        Returns:
            Job object ready to be saved
        """
        return Job(
            source=self.source_name,
            source_job_id=parsed_data.get("source_job_id"),
            title=parsed_data.get("title"),
            company=parsed_data.get("company"),
            department=parsed_data.get("department"),
            location=parsed_data.get("location"),
            remote=parsed_data.get("remote"),
            salary_min=parsed_data.get("salary_min"),
            salary_max=parsed_data.get("salary_max"),
            description=parsed_data.get("description"),
            requirements=parsed_data.get("requirements"),
            nice_to_haves=parsed_data.get("nice_to_haves"),
            apply_url=parsed_data.get("apply_url"),
            posted_date=parsed_data.get("posted_date"),
            scraped_at=datetime.utcnow(),
            company_industry=parsed_data.get("company_industry"),
            company_size=parsed_data.get("company_size"),
            source_type=parsed_data.get("source_type", "aggregator"),
        )
