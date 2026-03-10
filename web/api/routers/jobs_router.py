"""Job browsing routes."""

from typing import List, Optional

from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.job import JobOut, MatchScoreOut
from sqlalchemy.orm import Session

from src.job_searcher import JobSearcher
from src.models import Application, Job, JobMatch, User

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _attach_match(job: Job, user_id: int, db: Session) -> JobOut:
    """Build a JobOut, attaching this user's match scores."""
    out = JobOut.model_validate(job)
    match = (
        db.query(JobMatch)
        .filter(JobMatch.job_id == job.id, JobMatch.user_id == user_id)
        .first()
    )
    if match:
        out.match = MatchScoreOut.model_validate(match)
    return out


@router.get("", response_model=List[JobOut])
def list_jobs(
    keywords: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    remote: Optional[str] = Query(None, description="remote / hybrid / onsite"),
    min_score: Optional[float] = Query(None, alias="min_score"),
    sort: str = Query("score", description="score or date"),
    page: int = Query(1, ge=1, le=500),
    page_size: int = Query(20, ge=1, le=100),
    exclude_statuses: List[str] = Query(
        default=[],
        description="Hide jobs where user has an application with this status",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return paginated jobs with this user's match scores."""
    searcher = JobSearcher(db)
    # page_size + offset emulated via limit; JobSearcher doesn't have native pagination
    jobs = searcher.search(
        keywords=keywords,
        location=location,
        remote=remote,
        min_match_score=min_score,
        sort_by=sort,
        limit=page_size * page,  # over-fetch then slice
        user_id=current_user.id,
    )

    if exclude_statuses:
        excluded_job_ids = {
            row.job_id
            for row in db.query(Application.job_id)
            .filter(
                Application.user_id == current_user.id,
                Application.status.in_(exclude_statuses),
            )
            .all()
        }
        jobs = [j for j in jobs if j.id not in excluded_job_ids]

    start = (page - 1) * page_size
    page_jobs = jobs[start : start + page_size]
    return [_attach_match(j, current_user.id, db) for j in page_jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a single job with this user's match breakdown."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _attach_match(job, current_user.id, db)
