"""GitHub Jobs scraper."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper


class GitHubJobsScraper(BaseScraper):
    """Scraper for GitHub Jobs board (jobs.github.com).

    Uses the GitHub Jobs public API which doesn't require authentication.
    """

    GITHUB_JOBS_API = "https://jobs.github.com/positions.json"
    PAGE_SIZE = 50  # GitHub Jobs API default

    def __init__(self, session: Session):
        """Initialize GitHub Jobs scraper.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)
        self.base_url = self.GITHUB_JOBS_API

    def _get_source_name(self) -> str:
        """Get the name of the job source.

        Returns:
            'github'
        """
        return "github"

    def _fetch_jobs(
        self,
        description: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 0,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from GitHub Jobs API.

        Args:
            description: Job description keyword filter
            location: Location filter
            page: Page number for pagination

        Returns:
            List of raw job data from API
        """
        params: Dict[str, Any] = {"page": page}
        if description:
            params["description"] = description
        if location:
            params["location"] = location

        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch GitHub Jobs: {e}") from e

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse GitHub Jobs API response into standardized format.

        Args:
            raw_job: Raw job data from GitHub API

        Returns:
            Parsed job data with standardized fields
        """
        # Parse posted date (GitHub provides relative date, use current time)
        posted_date = datetime.utcnow()
        if "created_at" in raw_job:
            try:
                posted_date = datetime.fromisoformat(
                    raw_job["created_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                pass

        # Extract requirements from description (simple keyword matching)
        description = raw_job.get("description", "")
        requirements = self._extract_requirements(description)

        return {
            "source_job_id": raw_job.get("id"),
            "title": raw_job.get("title"),
            "company": raw_job.get("company"),
            "department": None,
            "location": raw_job.get("location"),
            "remote": "remote" if raw_job.get("type") == "Full Time" else None,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": None,
            "apply_url": raw_job.get("url"),
            "posted_date": posted_date,
            "company_industry": None,
            "company_size": None,
            "source_type": "aggregator",
        }

    def _extract_requirements(self, description: str) -> Optional[List[str]]:
        """Extract technology/skill requirements from job description.

        Args:
            description: Job description HTML

        Returns:
            List of requirements
        """
        # Simple extraction of common tech keywords
        keywords = [
            "python",
            "javascript",
            "typescript",
            "java",
            "go",
            "rust",
            "c++",
            "csharp",
            "c#",
            "sql",
            "react",
            "vue",
            "angular",
            "node",
            "express",
            "django",
            "flask",
            "fastapi",
            "aws",
            "gcp",
            "azure",
            "docker",
            "kubernetes",
            "git",
            "linux",
            "postgresql",
            "mongodb",
            "redis",
            "elasticsearch",
            "graphql",
            "rest api",
            "microservices",
            "agile",
            "ci/cd",
            "jenkins",
            "terraform",
        ]

        desc_lower = description.lower()
        found_keywords = [keyword for keyword in keywords if keyword in desc_lower]
        return found_keywords if found_keywords else None

    def scrape_by_keywords(
        self,
        keywords: List[str],
        location: Optional[str] = None,
        max_pages: int = 5,
    ) -> int:
        """Scrape GitHub Jobs for multiple keywords.

        Args:
            keywords: List of job description keywords to search
            location: Optional location filter
            max_pages: Maximum pages to scrape per keyword

        Returns:
            Total number of jobs scraped
        """
        total_jobs = 0

        for keyword in keywords:
            for page in range(max_pages):
                try:
                    jobs = self.scrape(
                        description=keyword, location=location, page=page
                    )
                    total_jobs += len(jobs)

                    # Stop if we got fewer results than expected (last page)
                    if len(jobs) < self.PAGE_SIZE:
                        break

                except Exception as e:
                    print(f"Error scraping page {page} for '{keyword}': {e}")
                    break

        return total_jobs
