"""Greenhouse job board scraper.

Greenhouse is an ATS (Applicant Tracking System) used by many tech companies.
Their job board API is publicly accessible and returns JSON data.

API docs: https://developers.greenhouse.io/job-board.html
Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.greenhouse")

# Companies using Greenhouse with confirmed public job boards.
# Covers a broad range of industries to serve diverse user profiles.
DEFAULT_BOARD_TOKENS = [
    # Enterprise tech & infrastructure
    "cloudflare",
    "hashicorp",
    "pagerduty",
    "servicenow",
    "atlassian",
    "okta",
    "postman",
    "gitlab",
    "dropbox",
    "figma",
    # Consulting & professional services
    "thoughtworks",
    "slalom",
    "publicissapient",
    # Fintech & financial services
    "robinhood",
    "adyen",
    "n26",
    # Data & analytics
    "fivetran",
    # Media, social & consumer
    "reddit",
    "pinterest",
    "discord",
    "twitch",
    "duolingo",
    "airbnb",
    # Gaming
    "riotgames",
    # Marketplace & delivery
    "lyft",
    "intercom",
    # Healthcare
    "oscar",
    # Logistics & supply chain
    "flexport",
    "project44",
    "shippeo",
    # European tech
    "booking",
    "criteo",
    "deliveroo",
    "typeform",
]

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseScraper(BaseScraper):
    """Scraper for Greenhouse-hosted job boards.

    Fetches jobs from multiple companies that use Greenhouse as their ATS.
    The API is public and requires no authentication.
    """

    def __init__(self, session: Session, board_tokens: Optional[List[str]] = None):
        super().__init__(session)
        self.board_tokens = board_tokens or DEFAULT_BOARD_TOKENS

    def _get_source_name(self) -> str:
        return "greenhouse"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from all configured Greenhouse boards.

        Kwargs:
            board_tokens: Override default board tokens list
            keywords: Filter jobs by keyword in title (applied client-side)

        Returns:
            List of raw job dicts from the Greenhouse API
        """
        board_tokens = kwargs.get("board_tokens", self.board_tokens)
        all_jobs: List[Dict[str, Any]] = []

        for token in board_tokens:
            try:
                url = f"{GREENHOUSE_API_BASE}/{token}/jobs"
                params = {"content": "true"}
                resp = requests.get(url, params=params, timeout=15)

                if resp.status_code == 404:
                    logger.debug(f"Board not found: {token}")
                    continue
                if resp.status_code != 200:
                    logger.warning(
                        f"Greenhouse API error for {token}: HTTP {resp.status_code}"
                    )
                    continue

                data = resp.json()
                jobs = data.get("jobs", [])

                # Tag each job with the board token (company)
                for job in jobs:
                    job["_board_token"] = token

                all_jobs.extend(jobs)
                logger.info(f"Fetched {len(jobs)} jobs from {token}")

            except requests.RequestException as e:
                logger.warning(f"Failed to fetch from {token}: {e}")
                continue

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Greenhouse API job object into standardized format."""
        board_token = raw_job.get("_board_token", "unknown")

        # Extract location from the first location object
        location = None
        locations = raw_job.get("location", {})
        if isinstance(locations, dict):
            location = locations.get("name")

        # Determine remote status from location string
        remote = None
        if location:
            loc_lower = location.lower()
            if "remote" in loc_lower:
                remote = "remote"
            elif "hybrid" in loc_lower:
                remote = "hybrid"

        # Extract departments
        department = None
        departments = raw_job.get("departments", [])
        if departments:
            department = departments[0].get("name")

        # Parse HTML content to plain text and extract requirements
        description = ""
        content = raw_job.get("content", "")
        if content:
            soup = BeautifulSoup(content, "html.parser")
            description = soup.get_text(separator="\n").strip()

        requirements = self._extract_requirements(description)

        # Parse updated date
        posted_date = datetime.utcnow()
        updated_at = raw_job.get("updated_at")
        if updated_at:
            try:
                posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Build apply URL
        apply_url = raw_job.get("absolute_url", "")

        # Company name from board token (title-cased)
        company = board_token.replace("-", " ").title()

        return {
            "source_job_id": str(raw_job.get("id", "")),
            "title": raw_job.get("title", ""),
            "company": company,
            "department": department,
            "location": location,
            "remote": remote,
            "salary_min": None,
            "salary_max": None,
            "description": description[:5000] if description else None,
            "requirements": requirements,
            "nice_to_haves": None,
            "apply_url": apply_url,
            "posted_date": posted_date,
            "company_industry": "Technology",
            "company_size": None,
            "source_type": "company_portal",
        }

    def _extract_requirements(self, description: str) -> Optional[List[str]]:
        """Extract technology/skill requirements from job description."""
        if not description:
            return None

        keywords = [
            "python",
            "javascript",
            "typescript",
            "java",
            "c++",
            "c#",
            "golang",
            "go",
            "rust",
            "ruby",
            "scala",
            "kotlin",
            "swift",
            "sql",
            "nosql",
            "postgresql",
            "mysql",
            "mongodb",
            "redis",
            "dynamodb",
            "elasticsearch",
            "aws",
            "azure",
            "gcp",
            "google cloud",
            "react",
            "angular",
            "vue",
            "next.js",
            "node.js",
            "django",
            "flask",
            "fastapi",
            "spring",
            "rails",
            "docker",
            "kubernetes",
            "terraform",
            "ansible",
            "git",
            "ci/cd",
            "jenkins",
            "github actions",
            "rest",
            "graphql",
            "grpc",
            "microservices",
            "machine learning",
            "deep learning",
            "pytorch",
            "tensorflow",
            "data engineering",
            "spark",
            "airflow",
            "kafka",
            "agile",
            "scrum",
            "linux",
            "unix",
        ]

        desc_lower = description.lower()
        found = [kw for kw in keywords if kw in desc_lower]
        return found if found else None

    def scrape_by_keywords(
        self,
        keywords: List[str],
        location: Optional[str] = None,
        max_pages: int = 1,
    ) -> int:
        """Scrape Greenhouse boards and filter by keywords.

        Args:
            keywords: List of keywords to filter jobs by (matched against title)
            location: Optional location filter
            max_pages: Unused (Greenhouse returns all jobs per board)

        Returns:
            Total number of new jobs added
        """
        raw_jobs = self._fetch_jobs()

        # Filter by keywords (match against title and description)
        filtered = []
        kw_lower = [k.lower() for k in keywords]
        for job in raw_jobs:
            title = (job.get("title") or "").lower()
            content = (job.get("content") or "").lower()
            loc = ""
            if isinstance(job.get("location"), dict):
                loc = (job["location"].get("name") or "").lower()

            if any(kw in title or kw in content for kw in kw_lower):
                if location and location.lower() not in loc:
                    continue
                filtered.append(job)

        # Now run filtered jobs through the standard parse/persist pipeline
        try:
            self._record_metric("fetch_attempt", 1, f"keywords={keywords}")
        except Exception:
            pass

        jobs_added = 0
        for raw_job in filtered:
            try:
                parsed = self._parse_job(raw_job)
                if self._job_exists(parsed):
                    continue
                job = self._create_job_object(parsed)
                self.session.add(job)
                jobs_added += 1
            except Exception as e:
                logger.warning(f"Error parsing Greenhouse job: {e}")
                continue

        if jobs_added:
            self.session.commit()
            try:
                self._record_metric("jobs_added", jobs_added, None)
            except Exception:
                pass

        return jobs_added
