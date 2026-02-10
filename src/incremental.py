"""Incremental scraping and notifications system."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.job_scrapers.github_scraper import GitHubJobsScraper
from src.job_scrapers.microsoft_scraper import MicrosoftScraper
from src.models import Job, JobMatch, User

logger = logging.getLogger("jobhunter.incremental")


class IncrementalScraper:
    """Wrapper for incremental scraping (only fetch new jobs since last run)."""

    def __init__(self, session: Session):
        self.session = session

    def scrape_incremental(
        self, source: str, lookback_hours: int = 24, **kwargs
    ) -> int:
        """Scrape only jobs posted in the last N hours.

        Args:
            source: 'github' or 'microsoft'
            lookback_hours: Only fetch jobs posted in last N hours (default 24)
            **kwargs: Additional arguments to pass to scraper

        Returns:
            Number of new jobs added
        """
        scraper_map = {"github": GitHubJobsScraper, "microsoft": MicrosoftScraper}

        cls = scraper_map.get(source)
        if not cls:
            raise ValueError(f"Unknown source: {source}")

        scraper = cls(self.session)

        # Run scraper
        jobs = scraper.scrape(**kwargs)

        # Filter jobs to only those posted recently
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
        new_jobs = [j for j in jobs if j.posted_date and j.posted_date >= cutoff]

        logger.info(
            f"Incremental scrape {source}: {len(jobs)} total, "
            f"{len(new_jobs)} from last {lookback_hours}h"
        )
        return len(new_jobs)


class SimpleNotifier:
    """Simple notification system for high-match jobs."""

    def __init__(self, session: Session):
        self.session = session

    def notify_high_matches(self, user: User, min_score: float = 80.0) -> list:
        """Get high-match jobs for a user (score >= min_score).

        Args:
            user: User instance
            min_score: Minimum match score threshold

        Returns:
            List of (Job, JobMatch) tuples for high-scoring jobs
        """
        matches = (
            self.session.query(Job, JobMatch)
            .join(JobMatch, Job.id == JobMatch.job_id)
            .filter(JobMatch.user_id == user.id, JobMatch.match_score >= min_score)
            .all()
        )

        logger.info(
            f"High-match jobs for user {user.id}: "
            f"{len(matches)} jobs with score >= {min_score}"
        )
        return matches

    def format_notification(self, job: Job, match: JobMatch) -> str:
        """Format a notification message for a job match.

        Args:
            job: Job instance
            match: JobMatch instance

        Returns:
            Formatted notification string
        """
        msg = (
            f"🎯 High Match: {job.title} at {job.company}\n"
            f"   Score: {match.match_score:.1f}/100\n"
            f"   Location: {job.location or 'N/A'}\n"
            f"   Remote: {job.remote or 'N/A'}\n"
            f"   Link: {job.apply_url or 'N/A'}"
        )
        return msg


__all__ = ["IncrementalScraper", "SimpleNotifier"]
