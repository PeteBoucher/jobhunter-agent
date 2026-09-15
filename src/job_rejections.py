"""Tracks jobs a user has explicitly marked as not of interest.

Distinct from ``ApplicationTracker.reject_application`` (which records that an
*employer* rejected the candidate) — this is the user rejecting a job outright,
applied to or not. Feeds ``job_matcher._load_rejection_signals`` so similar
future jobs score lower. See CLAUDE.md's "Matching formula" section.

``user_id=None`` means legacy single-user CLI mode (unscoped, matching
``ApplicationTracker``'s convention) — the web API always passes a real
``user_id``.
"""

from typing import List, Optional, Set

from sqlalchemy.orm import Query, Session

from src.models import Job, RejectedJob


def _user_filter(query: Query, user_id: Optional[int]) -> Query:
    if user_id is not None:
        query = query.filter(RejectedJob.user_id == user_id)
    return query


def reject_job(
    session: Session,
    user_id: Optional[int],
    job_id: int,
    reason: Optional[str] = None,
) -> RejectedJob:
    """Record (or update) a rejection. Idempotent per (user_id, job_id)."""
    row = _user_filter(
        session.query(RejectedJob).filter(RejectedJob.job_id == job_id), user_id
    ).first()
    if row:
        if reason is not None:
            row.reason = reason
        session.commit()
        return row

    row = RejectedJob(user_id=user_id, job_id=job_id, reason=reason)
    session.add(row)
    session.commit()
    return row


def unreject_job(session: Session, user_id: Optional[int], job_id: int) -> bool:
    """Undo a rejection. Returns True if a row was deleted, False if none existed."""
    row = _user_filter(
        session.query(RejectedJob).filter(RejectedJob.job_id == job_id), user_id
    ).first()
    if not row:
        return False
    session.delete(row)
    session.commit()
    return True


def get_rejected_jobs(
    session: Session, user_id: Optional[int], limit: int = 100
) -> List[Job]:
    """Return jobs this user rejected, newest rejection first."""
    query = session.query(Job).join(RejectedJob, RejectedJob.job_id == Job.id)
    query = _user_filter(query, user_id)
    return query.order_by(RejectedJob.created_at.desc()).limit(limit).all()


def get_rejected_job_ids(session: Session, user_id: int) -> Set[int]:
    """Return the set of job ids this user has rejected (for feed filtering)."""
    return {
        row.job_id
        for row in session.query(RejectedJob.job_id)
        .filter(RejectedJob.user_id == user_id)
        .all()
    }


__all__ = [
    "reject_job",
    "unreject_job",
    "get_rejected_jobs",
    "get_rejected_job_ids",
]
