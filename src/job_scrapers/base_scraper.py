"""Base scraper abstract class for all job scrapers."""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.models import Job, ScraperMetric

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
                # record attempt
                try:
                    self._record_metric("fetch_attempt", 1, f"attempt={attempt}")
                except Exception:
                    logger.debug("Failed to record fetch_attempt metric")
                try:
                    raw_jobs = self._fetch_jobs(**kwargs)
                    # success
                    try:
                        self._record_metric("fetch_success", 1, f"attempt={attempt}")
                    except Exception:
                        logger.debug("Failed to record fetch_success metric")
                    break
                except Exception as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        try:
                            self._record_metric("retry", 1, f"attempt={attempt}")
                        except Exception:
                            logger.debug("Failed to record retry metric")
                        sleep_time = backoff * (2**attempt)
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise

            if raw_jobs is None:
                raise RuntimeError(
                    f"Failed to fetch jobs from {self.source_name}: {last_exc}"
                )

            jobs: List[Job] = []

            for raw_job in raw_jobs:
                try:
                    # Parse job data
                    parsed_data = self._parse_job(raw_job)

                    # count parsed
                    try:
                        self._record_metric(
                            "jobs_parsed", 1, parsed_data.get("source_job_id")
                        )
                    except Exception:
                        logger.debug("Failed to record jobs_parsed metric")

                    # Check if job already exists
                    existing_job = self._job_exists(parsed_data)
                    if existing_job:
                        continue

                    # Create Job object
                    job = self._create_job_object(parsed_data)
                    jobs.append(job)

                except Exception as e:
                    logger.exception(f"Error parsing job from {self.source_name}: {e}")
                    try:
                        self._record_metric("parse_error", 1, str(e))
                    except Exception:
                        logger.debug("Failed to record parse_error metric")
                    continue
            # Save all jobs to database
            if jobs:
                self.session.add_all(jobs)
                self.session.commit()
                try:
                    self._record_metric("jobs_added", len(jobs), None)
                except Exception:
                    logger.debug("Failed to record jobs_added metric")
            return jobs

        except Exception as e:
            try:
                self._record_metric("fetch_fail", 1, str(e))
            except Exception:
                logger.debug("Failed to record fetch_fail metric")
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

    def _job_exists(self, parsed_data: dict) -> Optional[Job]:
        """Check if job already exists in database.

        Args:
            parsed_data: Parsed job data

        Returns:
            Existing Job object or None if doesn't exist
        """
        return (
            self.session.query(Job)
            .filter(
                Job.source == self.source_name,
                Job.source_job_id == parsed_data.get("source_job_id"),
            )
            .first()
        )

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
