"""Lever job board scraper.

Lever is an ATS used by many tech companies. Their public postings API
returns JSON data for all open positions at a company.

Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy.orm import Session

from src.job_scrapers.base_scraper import BaseScraper

logger = logging.getLogger("jobhunter.scrapers.lever")

# Companies using Lever with confirmed public job boards.
DEFAULT_COMPANY_SLUGS = [
    # QA / testing tooling
    "browserstack",
    "saucelabs",
    # Enterprise & consulting
    "capgemini",
    "sap",
    # European tech
    "remote",
    "hotjar",
    "personio",
    "relayr",
    # Media & consumer
    "spotify",
    # Media delivery & imaging
    "cloudinary",
]

LEVER_API_BASE = "https://api.lever.co/v0/postings"


class LeverScraper(BaseScraper):
    """Scraper for Lever-hosted job boards.

    Fetches jobs from multiple companies that use Lever as their ATS.
    The API is public and requires no authentication.
    """

    def __init__(self, session: Session, company_slugs: Optional[List[str]] = None):
        super().__init__(session)
        self.company_slugs = company_slugs or DEFAULT_COMPANY_SLUGS

    def _get_source_name(self) -> str:
        return "lever"

    def _fetch_jobs(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """Fetch jobs from all configured Lever company pages.

        Kwargs:
            company_slugs: Override default company slugs list

        Returns:
            List of raw job dicts from the Lever API
        """
        company_slugs = kwargs.get("company_slugs", self.company_slugs)
        all_jobs: List[Dict[str, Any]] = []

        for slug in company_slugs:
            try:
                url = f"{LEVER_API_BASE}/{slug}"
                params = {"mode": "json"}
                resp = requests.get(url, params=params, timeout=15)

                if resp.status_code == 404:
                    logger.debug(f"Company not found on Lever: {slug}")
                    continue
                if resp.status_code != 200:
                    logger.warning(
                        f"Lever API error for {slug}: HTTP {resp.status_code}"
                    )
                    continue

                jobs = resp.json()
                if not isinstance(jobs, list):
                    logger.warning(f"Unexpected Lever response for {slug}")
                    continue

                # Tag each job with the company slug
                for job in jobs:
                    job["_company_slug"] = slug

                all_jobs.extend(jobs)
                logger.info(f"Fetched {len(jobs)} jobs from {slug}")

            except requests.RequestException as e:
                logger.warning(f"Failed to fetch from {slug}: {e}")
                continue

        return all_jobs

    def _parse_job(self, raw_job: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a Lever API posting object into standardized format."""
        company_slug = raw_job.get("_company_slug", "unknown")

        # Categories contain location, department, team, commitment
        categories = raw_job.get("categories", {})
        location = categories.get("location")
        department = categories.get("department") or categories.get("team")
        # Determine remote status
        remote = None
        if location:
            loc_lower = location.lower()
            if "remote" in loc_lower:
                remote = "remote"
            elif "hybrid" in loc_lower:
                remote = "hybrid"

        # Description - Lever provides descriptionPlain or description (HTML)
        description = raw_job.get("descriptionPlain", "")
        if not description:
            description = raw_job.get("description", "")

        # Extract requirements from lists (Lever provides structured lists)
        requirements = self._extract_requirements_from_lists(raw_job)
        if not requirements:
            requirements = self._extract_requirements(description)

        # Parse creation timestamp (milliseconds since epoch)
        posted_date = datetime.utcnow()
        created_at = raw_job.get("createdAt")
        if created_at and isinstance(created_at, (int, float)):
            try:
                posted_date = datetime.utcfromtimestamp(created_at / 1000)
            except (ValueError, OSError):
                pass

        # Apply URL
        apply_url = raw_job.get("applyUrl") or raw_job.get("hostedUrl", "")

        # Company name from slug
        company = company_slug.replace("-", " ").title()

        return {
            "source_job_id": raw_job.get("id", ""),
            "title": raw_job.get("text", ""),
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

    def _extract_requirements_from_lists(
        self, raw_job: Dict[str, Any]
    ) -> Optional[List[str]]:
        """Extract requirements from Lever's structured lists field."""
        lists = raw_job.get("lists", [])
        if not lists:
            return None

        requirements = []
        for lst in lists:
            text = (lst.get("text") or "").lower()
            # Look for requirement-like sections
            if any(
                kw in text
                for kw in [
                    "requirement",
                    "qualif",
                    "what you",
                    "you have",
                    "you bring",
                    "must have",
                    "skills",
                    "experience",
                ]
            ):
                items = lst.get("content", "")
                if isinstance(items, str):
                    # Split by newlines or list markers
                    for line in items.split("\n"):
                        line = line.strip().lstrip("•-*")
                        if line and len(line) > 5:
                            requirements.append(line.strip())

        return requirements[:20] if requirements else None

    def _extract_requirements(self, description: str) -> Optional[List[str]]:
        """Extract technology/skill requirements from job description text."""
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
        """Scrape Lever boards and filter by keywords.

        Args:
            keywords: List of keywords to filter jobs by
            location: Optional location filter
            max_pages: Unused (Lever returns all jobs per company)

        Returns:
            Total number of new jobs added
        """
        raw_jobs = self._fetch_jobs()

        # Filter by keywords
        filtered = []
        kw_lower = [k.lower() for k in keywords]
        for job in raw_jobs:
            title = (job.get("text") or "").lower()
            desc = (job.get("descriptionPlain") or "").lower()
            categories = job.get("categories", {})
            loc = (categories.get("location") or "").lower()

            if any(kw in title or kw in desc for kw in kw_lower):
                if location and location.lower() not in loc:
                    continue
                filtered.append(job)

        existing_ids = self._load_existing_ids()

        jobs_added = 0
        for raw_job in filtered:
            try:
                parsed = self._parse_job(raw_job)
                if parsed.get("source_job_id") in existing_ids:
                    continue
                job = self._create_job_object(parsed)
                self.session.add(job)
                existing_ids.add(parsed.get("source_job_id"))
                jobs_added += 1
            except Exception as e:
                logger.warning(f"Error parsing Lever job: {e}")
                continue

        if jobs_added:
            self.session.commit()
            try:
                self._record_metric("jobs_added", jobs_added, None)
            except Exception:
                pass

        return jobs_added
