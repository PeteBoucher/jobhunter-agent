"""Job browsing routes."""

import re
from typing import Any, Dict, List, Optional, Tuple

from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.job import JobOut, MatchScoreOut, OtherLocationOut
from schemas.rejection import RejectionCreate, RejectionOut
from sqlalchemy.orm import Session

from src.job_rejections import (
    get_rejected_job_ids,
    get_rejected_jobs,
    reject_job,
    unreject_job,
)
from src.job_searcher import JobSearcher
from src.models import Application, Job, JobMatch, RejectedJob, User

router = APIRouter(prefix="/jobs", tags=["jobs"])

# GET /jobs over-fetches this many times page_size * page before grouping, so
# that collapsing multi-location postings still leaves enough cards to fill
# the requested page. Groups beyond the over-fetch window are simply cut off.
_GROUP_OVERFETCH = 3

_DASHES = re.compile(r"[\u2010-\u2015\u2212-]")
_SPACES = re.compile(r"\s+")

GroupKey = Tuple[str, str, str]


def _group_key(job: Job) -> GroupKey:
    """Key identifying one role posted in several locations.

    Employers often post the same role once per city/country (separate ATS
    postings, same title, identical scores) — these flood the feed. Jobs with
    the same company, normalised title and remote type are shown as one card.
    `remote` is part of the key so a remote and an onsite role stay separate.
    """
    title = _DASHES.sub("-", (job.title or "").lower())
    title = _SPACES.sub(" ", title).strip()
    company = _SPACES.sub(" ", (job.company or "").lower()).strip()
    return (company, title, (job.remote or "").lower())


def _group_jobs(jobs: List[Job]) -> List[Tuple[Job, List[Job]]]:
    """Group ordered jobs by _group_key, keeping the first of each group (best
    by the current sort order) as the representative."""
    groups: Dict[GroupKey, Tuple[Job, List[Job]]] = {}
    for job in jobs:
        key = _group_key(job)
        if key in groups:
            groups[key][1].append(job)
        else:
            groups[key] = (job, [])
    return list(groups.values())


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
    # For hybrid/onsite, fall back to all of the user's preferred locations when
    # no explicit location filter was provided. Use a list so the searcher can
    # OR them together — passing only the first would silently exclude the rest.
    location_filter: Any = location
    if remote in ("hybrid", "onsite") and not location:
        locs: List[str] = []
        if current_user.location:
            locs.append(current_user.location)
        if current_user.preferences and current_user.preferences.preferred_locations:
            locs.extend(current_user.preferences.preferred_locations)
        location_filter = locs if locs else None

    # For remote searches, restrict to jobs the user is eligible for based on
    # their preferred_countries. Jobs with no country (global ATS roles) are
    # always included. If the user hasn't set any preferred countries, no
    # restriction is applied.
    eligible_countries = None
    if remote == "remote":
        prefs = current_user.preferences
        if prefs and prefs.preferred_countries:
            eligible_countries = [c.lower() for c in prefs.preferred_countries]

    searcher = JobSearcher(db)
    # page_size + offset emulated via limit; JobSearcher doesn't have native pagination
    jobs = searcher.search(
        keywords=keywords,
        location=location_filter,
        remote=remote,
        eligible_countries=eligible_countries,
        min_match_score=min_score,
        sort_by=sort,
        # over-fetch then group and slice — see _GROUP_OVERFETCH
        limit=page_size * page * _GROUP_OVERFETCH,
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

    # Jobs the user explicitly marked "not interested" are hidden unconditionally
    # (like inactive jobs) — not gated by exclude_statuses, distinct from
    # employer-side Application.status == "rejected" above. See GET /jobs/rejected
    # to view/undo them.
    #
    # Rejecting any posting of a multi-location role hides the whole group, so
    # "Not interested" on a card writes one RejectedJob row, not one per
    # sibling — several rows would trip the company-repetition rejection
    # penalty (job_matcher._load_rejection_signals) for that company's other
    # jobs.
    rejected_ids = get_rejected_job_ids(db, current_user.id)
    if rejected_ids:
        rejected_keys = {
            _group_key(j) for j in db.query(Job).filter(Job.id.in_(rejected_ids))
        }
        jobs = [
            j
            for j in jobs
            if j.id not in rejected_ids and _group_key(j) not in rejected_keys
        ]

    start = (page - 1) * page_size
    page_groups = _group_jobs(jobs)[start : start + page_size]
    out: List[JobOut] = []
    for rep, others in page_groups:
        job_out = _attach_match(rep, current_user.id, db)
        job_out.other_locations = [
            OtherLocationOut(id=o.id, location=o.location, country=o.country)
            for o in others
        ]
        out.append(job_out)
    return out


@router.get("/rejected", response_model=List[JobOut])
def list_rejected_jobs(
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return jobs this user marked "not interested", newest rejection first."""
    jobs = get_rejected_jobs(db, current_user.id, limit=limit)
    reasons = {
        row.job_id: row.reason
        for row in db.query(RejectedJob).filter(RejectedJob.user_id == current_user.id)
    }
    out = []
    for job in jobs:
        job_out = _attach_match(job, current_user.id, db)
        job_out.is_rejected = True
        job_out.rejection_reason = reasons.get(job.id)
        out.append(job_out)
    return out


@router.post("/{job_id}/reject", response_model=RejectionOut, status_code=201)
def reject_job_route(
    job_id: int,
    body: RejectionCreate = RejectionCreate(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a job not of interest. Idempotent — rejecting again updates the reason."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    row = reject_job(db, current_user.id, job_id, reason=body.reason)
    return RejectionOut.model_validate(row)


@router.delete("/{job_id}/reject", status_code=204)
def unreject_job_route(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Undo a rejection. No-op (still 204) if the job wasn't rejected."""
    unreject_job(db, current_user.id, job_id)


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
