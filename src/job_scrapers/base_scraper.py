"""Base scraper abstract class for all job scrapers."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models import Job


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
        """Main scraping method.

        Fetches jobs from the source, parses them, and stores in database.

        Args:
            **kwargs: Source-specific parameters

        Returns:
            List of Job objects that were scraped
        """
        try:
            # Fetch raw jobs from source
            raw_jobs = self._fetch_jobs(**kwargs)
            jobs = []

            for raw_job in raw_jobs:
                try:
                    # Parse job data
                    parsed_data = self._parse_job(raw_job)

                    # Check if job already exists
                    existing_job = self._job_exists(parsed_data)
                    if existing_job:
                        continue

                    # Create Job object
                    job = self._create_job_object(parsed_data)
                    jobs.append(job)

                except Exception as e:
                    print(f"Error parsing job from {self.source_name}: {e}")
                    continue

            # Save all jobs to database
            if jobs:
                self.session.add_all(jobs)
                self.session.commit()

            return jobs

        except Exception as e:
            self.session.rollback()
            raise RuntimeError(f"Error scraping {self.source_name}: {e}") from e

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
