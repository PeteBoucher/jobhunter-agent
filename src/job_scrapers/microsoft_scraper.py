"""Microsoft careers scraper."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper


class MicrosoftScraper(BaseScraper):
    """Scraper for Microsoft careers portal (careers.microsoft.com).

    Uses the public Microsoft careers API endpoint.
    """

    MICROSOFT_API = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
    MICROSOFT_CAREERS_URL = "https://careers.microsoft.com/us/en"

    def __init__(self, session: Session):
        """Initialize Microsoft careers scraper.

        Args:
            session: SQLAlchemy database session
        """
        super().__init__(session)

    def _get_source_name(self) -> str:
        """Get the name of the job source.

        Returns:
            'microsoft'
        """
        return "microsoft"

    def _fetch_jobs(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        page: int = 0,
        page_size: int = 20,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch jobs from Microsoft careers API.

        Args:
            keywords: Search keywords
            location: Location filter
            page: Page number for pagination
            page_size: Number of jobs per page

        Returns:
            List of raw job data from API
        """
        params: Dict[str, Any] = {
            "q": keywords or "",
            "p": page,
            "pagesize": page_size,
        }

        if location:
            params["l"] = location

        try:
            response = requests.get(
                self.MICROSOFT_API,
                params=params,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("operationResult", {}).get("result", {}).get("jobs", [])
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch Microsoft jobs: {e}") from e

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Microsoft API response into standardized format.

        Args:
            raw_job: Raw job data from Microsoft API

        Returns:
            Parsed job data with standardized fields
        """
        # Parse posted date
        posted_date = datetime.utcnow()
        if "postingDate" in raw_job:
            try:
                posted_date = datetime.fromisoformat(
                    raw_job["postingDate"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Extract description for requirements
        description = self._get_job_description(raw_job)
        requirements = self._extract_requirements(description)

        # Determine remote status
        remote = None
        location = raw_job.get("location", "")
        if location.lower() in ["remote", "virtual"]:
            remote = "remote"

        return {
            "source_job_id": raw_job.get("jobId"),
            "title": raw_job.get("title"),
            "company": "Microsoft",
            "department": raw_job.get("category"),
            "location": location,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": description,
            "requirements": requirements,
            "nice_to_haves": None,
            "apply_url": f"{self.MICROSOFT_CAREERS_URL}/jobs/{raw_job.get('jobId')}",
            "posted_date": posted_date,
            "company_industry": "Technology",
            "company_size": "Large Enterprise",
            "source_type": "company_portal",
        }

    def _get_job_description(self, raw_job: Dict[str, Any]) -> str:
        """Extract job description from raw job data.

        Args:
            raw_job: Raw job data from Microsoft API

        Returns:
            Job description text
        """
        # Microsoft API includes description in different fields
        description_parts = []

        if "description" in raw_job:
            description_parts.append(raw_job["description"])

        if "additionalInfo" in raw_job:
            description_parts.append(raw_job["additionalInfo"])

        # Join all parts and clean HTML tags if present
        description = " ".join(description_parts)

        # Basic HTML tag removal (Microsoft sometimes includes HTML)
        try:
            soup = BeautifulSoup(description, "html.parser")
            description = soup.get_text()
        except Exception:
            pass

        return description.strip()

    def _extract_requirements(self, description: str) -> Optional[List[str]]:
        """Extract technology/skill requirements from job description.

        Args:
            description: Job description text

        Returns:
            List of requirements
        """
        keywords = [
            "python",
            "javascript",
            "typescript",
            "java",
            "c++",
            "csharp",
            "c#",
            "golang",
            "rust",
            "sql",
            "azure",
            "aws",
            "gcp",
            ".net",
            "asp.net",
            "react",
            "angular",
            "vue",
            "node",
            "express",
            "docker",
            "kubernetes",
            "git",
            "rest api",
            "graphql",
            "microservices",
            "agile",
            "scrum",
            "jira",
            "linux",
            "windows server",
            "postgresql",
            "sql server",
            "mongodb",
            "cosmosdb",
        ]

        desc_lower = description.lower()
        found_keywords = [keyword for keyword in keywords if keyword in desc_lower]
        return found_keywords if found_keywords else None

    def scrape_by_keywords(
        self,
        keywords: List[str],
        location: Optional[str] = None,
        max_pages: int = 3,
    ) -> int:
        """Scrape Microsoft careers for multiple keywords.

        Args:
            keywords: List of job search keywords
            location: Optional location filter
            max_pages: Maximum pages to scrape per keyword

        Returns:
            Total number of jobs scraped
        """
        total_jobs = 0

        for keyword in keywords:
            for page in range(max_pages):
                try:
                    jobs = self.scrape(keywords=keyword, location=location, page=page)
                    total_jobs += len(jobs)

                    # Stop if we got no results (last page)
                    if len(jobs) == 0:
                        break

                except Exception as e:
                    print(f"Error scraping page {page} for '{keyword}': {e}")
                    break

        return total_jobs
