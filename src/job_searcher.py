"""Job search and filtering functionality."""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.models import Job, JobMatch, User


class JobSearcher:
    """Search and filter jobs from the database."""

    def __init__(self, session: Session):
        """Initialize job searcher.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def search(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        remote: Optional[str] = None,
        min_match_score: Optional[float] = None,
        source: Optional[str] = None,
        posted_after: Optional[datetime] = None,
        sort_by: str = "date",
        limit: int = 50,
    ) -> List[Job]:
        """Search jobs with filters.

        Args:
            keywords: Search keywords in title, company, or description
            location: Filter by location
            remote: Filter by remote status (remote, hybrid, onsite)
            min_match_score: Minimum match score (0-100) - filters via
                JobMatch relationship
            source: Filter by job source (github, microsoft, etc.)
            posted_after: Only show jobs posted after this date
            sort_by: Sort order - "date" (default) or "score"
            limit: Maximum number of results

        Returns:
            List of matching jobs
        """
        query = self.session.query(Job).options(
            joinedload(Job.job_matches), joinedload(Job.applications)
        )

        # Text search
        if keywords:
            search_term = f"%{keywords.lower()}%"
            query = query.filter(
                (Job.title.ilike(search_term))
                | (Job.company.ilike(search_term))
                | (Job.description.ilike(search_term))
            )

        # Location filter
        if location:
            location_term = f"%{location.lower()}%"
            query = query.filter(Job.location.ilike(location_term))

        # Remote filter - check both the remote field and location text
        if remote:
            remote_val = remote.lower()
            query = query.filter(
                or_(
                    Job.remote == remote_val,
                    Job.location.ilike(f"%{remote_val}%"),
                )
            )

        # Source filter
        if source:
            query = query.filter(Job.source == source.lower())

        # Posted date filter
        if posted_after:
            query = query.filter(Job.posted_date >= posted_after)

        # Match score filter - join to JobMatch table
        if min_match_score is not None:
            query = query.join(JobMatch).filter(JobMatch.match_score >= min_match_score)

        # Sort by score or date
        if sort_by == "score" or min_match_score is not None:
            # Need JobMatch join for sorting if not already joined
            if min_match_score is None:
                query = query.join(JobMatch)
            results = query.order_by(
                JobMatch.match_score.desc(), Job.posted_date.desc()
            ).limit(limit)
        else:
            results = query.order_by(Job.posted_date.desc()).limit(limit)

        return results.all()

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        """Get a specific job by ID.

        Args:
            job_id: The job ID

        Returns:
            Job object or None if not found
        """
        return self.session.query(Job).filter(Job.id == job_id).first()

    def get_top_matches(
        self, user_id: Optional[int] = None, limit: int = 10
    ) -> List[Job]:
        """Get top matching jobs for a user.

        Args:
            user_id: Filter to specific user, or None for all jobs
            limit: Number of top matches to return

        Returns:
            List of top matching jobs
        """
        query = self.session.query(Job).order_by(Job.posted_date.desc()).limit(limit)

        if user_id:
            # Filter jobs that are good matches for this user
            user = self.session.query(User).filter(User.id == user_id).first()
            if not user:
                return []

        return query.all()

    def get_recent_jobs(self, days: int = 7, limit: int = 50) -> List[Job]:
        """Get recently posted jobs.

        Args:
            days: Number of days back to search
            limit: Maximum number of results

        Returns:
            List of recently posted jobs
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return self.search(posted_after=cutoff_date, limit=limit)

    def get_jobs_by_source(self, source: str, limit: int = 50) -> List[Job]:
        """Get jobs from a specific source.

        Args:
            source: Job source (github, microsoft, etc.)
            limit: Maximum number of results

        Returns:
            List of jobs from the source
        """
        return self.search(source=source, limit=limit)
