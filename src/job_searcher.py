"""Job search and filtering functionality."""

from datetime import datetime
from typing import List, Optional, Union

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from src.models import Job, JobMatch


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
        location: Optional[Union[str, List[str]]] = None,
        remote: Optional[str] = None,
        eligible_countries: Optional[List[str]] = None,
        min_match_score: Optional[float] = None,
        source: Optional[str] = None,
        posted_after: Optional[datetime] = None,
        sort_by: str = "date",
        limit: int = 50,
        user_id: Optional[int] = None,
    ) -> List[Job]:
        """Search jobs with filters.

        Args:
            keywords: Search keywords in title, company, or description
            location: Filter by location (string or list of locations OR'd together)
            remote: Filter by remote status (remote, hybrid, onsite)
            eligible_countries: When provided, restrict remote jobs to those
                with no country set (globally open roles) or whose country
                matches one of these ISO2 codes (lowercase).
            min_match_score: Minimum match score (0-100) - filters via
                JobMatch relationship
            source: Filter by job source (github, microsoft, etc.)
            posted_after: Only show jobs posted after this date
            sort_by: Sort order - "date" (default) or "score"
            limit: Maximum number of results
            user_id: Scope JobMatch rows to this user (required for correct
                multi-user score filtering/sorting)

        Returns:
            List of matching jobs
        """
        query = (
            self.session.query(Job)
            .options(joinedload(Job.job_matches), joinedload(Job.applications))
            .filter(Job.is_active.is_(True))
        )

        # Text search
        if keywords:
            search_term = f"%{keywords.lower()}%"
            query = query.filter(
                (Job.title.ilike(search_term))
                | (Job.company.ilike(search_term))
                | (Job.description.ilike(search_term))
            )

        # Location filter — accepts a single string or a list (OR'd together)
        if location:
            locs = location if isinstance(location, list) else [location]
            query = query.filter(
                or_(*[Job.location.ilike(f"%{loc.lower()}%") for loc in locs])
            )

        # Remote filter
        if remote:
            remote_val = remote.lower()
            if remote_val == "onsite":
                # Onsite jobs rarely tag themselves as "onsite" — they just have
                # remote=NULL. Exclude jobs that are explicitly remote or hybrid.
                query = query.filter(or_(Job.remote.is_(None), Job.remote == "onsite"))
            else:
                query = query.filter(
                    or_(
                        Job.remote == remote_val,
                        Job.location.ilike(f"%{remote_val}%"),
                    )
                )

        # Country eligibility filter for remote jobs.
        # Jobs with no country (global ATS roles) are always included.
        # Jobs with a country are only included if that country is in the
        # user's preferred_countries list.
        if eligible_countries:
            query = query.filter(
                or_(
                    Job.country.is_(None),
                    Job.country.in_(eligible_countries),
                )
            )

        # Source filter
        if source:
            query = query.filter(Job.source == source.lower())

        # Posted date filter
        if posted_after:
            query = query.filter(Job.posted_date >= posted_after)

        # Match score / sort — always join with user scope when user_id is given
        needs_match_join = min_match_score is not None or sort_by == "score"
        if needs_match_join:
            query = query.join(JobMatch, Job.id == JobMatch.job_id)
            if user_id is not None:
                query = query.filter(JobMatch.user_id == user_id)
            if min_match_score is not None:
                query = query.filter(JobMatch.match_score >= min_match_score)
            results = query.order_by(
                JobMatch.match_score.desc(), Job.posted_date.desc()
            ).limit(limit)
        else:
            results = query.order_by(Job.posted_date.desc()).limit(limit)

        return results.all()

    def get_recent_jobs(self, days: int = 7, limit: int = 20) -> List[Job]:
        """Return jobs posted within the last N days, newest first."""
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)
        return (
            self.session.query(Job)
            .options(joinedload(Job.job_matches))
            .filter(Job.posted_date >= cutoff, Job.is_active.is_(True))
            .order_by(Job.posted_date.desc())
            .limit(limit)
            .all()
        )

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        """Get a specific job by ID.

        Args:
            job_id: The job ID

        Returns:
            Job object or None if not found
        """
        return self.session.query(Job).filter(Job.id == job_id).first()
