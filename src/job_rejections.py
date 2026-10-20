"""Tracks jobs a user has explicitly marked as not of interest.

Distinct from ``ApplicationTracker.reject_application`` (which records that an
*employer* rejected the candidate) — this is the user rejecting a job outright,
applied to or not. Feeds ``job_matcher._load_rejection_signals`` so similar
future jobs score lower. See CLAUDE.md's "Matching formula" section.

Every function is scoped to one ``user_id`` — there is no unscoped mode. A
rejection is one user's preference and must never read, update or delete
another user's rows (the CLI used to pass ``user_id=None`` here, which matched
any user's rejection of the same job).
"""

from datetime import datetime
from typing import List, Optional, Set

from sqlalchemy.orm import Query, Session

from src.models import Job, RejectedJob, User


def _user_filter(query: Query, user_id: int) -> Query:
    if user_id is None:
        raise ValueError("user_id is required — rejections are per-user")
    return query.filter(RejectedJob.user_id == user_id)


def _mark_rejections_changed(session: Session, user_id: int) -> None:
    """Flag this user's existing match scores for a rejection-penalty refresh."""
    session.query(User).filter(User.id == user_id).update(
        {"rejections_updated_at": datetime.utcnow()}, synchronize_session=False
    )


def reject_job(
    session: Session,
    user_id: int,
    job_id: int,
    reason: Optional[str] = None,
) -> RejectedJob:
    """Record (or update) a rejection. Idempotent per (user_id, job_id)."""
    row = _user_filter(
        session.query(RejectedJob).filter(RejectedJob.job_id == job_id), user_id
    ).first()
    if row:
        if reason is not None and reason != row.reason:
            row.reason = reason
            row.reason_vec = None  # re-embedded by the next match phase
            _mark_rejections_changed(session, user_id)
        session.commit()
        return row

    row = RejectedJob(user_id=user_id, job_id=job_id, reason=reason)
    session.add(row)
    _mark_rejections_changed(session, user_id)
    session.commit()
    return row


def unreject_job(session: Session, user_id: int, job_id: int) -> bool:
    """Undo a rejection. Returns True if a row was deleted, False if none existed."""
    row = _user_filter(
        session.query(RejectedJob).filter(RejectedJob.job_id == job_id), user_id
    ).first()
    if not row:
        return False
    session.delete(row)
    _mark_rejections_changed(session, user_id)
    session.commit()
    return True


def get_rejected_jobs(session: Session, user_id: int, limit: int = 100) -> List[Job]:
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
