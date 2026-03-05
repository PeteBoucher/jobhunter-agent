"""Job application tracking functionality."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models import Application, Job


class ApplicationTracker:
    """Track job applications.

    Pass ``user_id`` to scope all queries to a single user (required for the
    multi-user web API).  When ``user_id`` is ``None`` the tracker operates in
    legacy single-user mode and does not filter by user — this preserves
    backward-compatibility with the CLI commands.
    """

    def __init__(self, session: Session, user_id: Optional[int] = None):
        self.session = session
        self.user_id = user_id

    # ── internal helpers ────────────────────────────────────────────────────

    def _user_filter(self, query):
        if self.user_id is not None:
            query = query.filter(Application.user_id == self.user_id)
        return query

    def _get_or_create(self, job_id: int) -> Application:
        app = self._user_filter(
            self.session.query(Application).filter(Application.job_id == job_id)
        ).first()
        if not app:
            app = Application(job_id=job_id, user_id=self.user_id)
            self.session.add(app)
        return app

    # ── public API ──────────────────────────────────────────────────────────

    def save_job(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Save a job for later."""
        existing = self._user_filter(
            self.session.query(Application).filter(
                Application.job_id == job_id,
                Application.status == "saved",
            )
        ).first()
        if existing:
            return existing

        app = Application(
            job_id=job_id, user_id=self.user_id, status="saved", notes=notes
        )
        self.session.add(app)
        self.session.commit()
        return app

    def apply_to_job(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Record an application to a job."""
        existing = self._user_filter(
            self.session.query(Application)
            .filter(Application.job_id == job_id)
            .filter(Application.status != "saved")
        ).first()
        if existing:
            existing.status = "applied"
            existing.application_date = datetime.utcnow()
            existing.notes = notes
            self.session.commit()
            return existing

        app = Application(
            job_id=job_id,
            user_id=self.user_id,
            status="applied",
            application_date=datetime.utcnow(),
            notes=notes,
        )
        self.session.add(app)
        self.session.commit()
        return app

    def schedule_interview(
        self, job_id: int, interview_date: datetime, notes: Optional[str] = None
    ) -> Application:
        """Schedule an interview for a job."""
        app = self._get_or_create(job_id)
        app.status = "interview_scheduled"
        if notes:
            app.notes = notes
        self.session.commit()
        return app

    def mark_interviewed(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Mark a job as interviewed."""
        app = self._get_or_create(job_id)
        app.status = "interviewed"
        if notes:
            app.notes = notes
        self.session.commit()
        return app

    def reject_application(
        self, job_id: int, reason: Optional[str] = None
    ) -> Application:
        """Mark an application as rejected."""
        app = self._get_or_create(job_id)
        app.status = "rejected"
        if reason:
            app.notes = reason
        self.session.commit()
        return app

    def offer_received(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Mark that an offer was received for a job."""
        app = self._get_or_create(job_id)
        app.status = "offer"
        if notes:
            app.notes = notes
        self.session.commit()
        return app

    def get_application(self, job_id: int) -> Optional[Application]:
        """Get application record for a job."""
        return self._user_filter(
            self.session.query(Application).filter(Application.job_id == job_id)
        ).first()

    def get_applications_by_status(
        self, status: str, limit: int = 50
    ) -> List[Application]:
        """Get applications by status."""
        return (
            self._user_filter(
                self.session.query(Application).filter(Application.status == status)
            )
            .order_by(Application.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_all_applications(self, limit: int = 200) -> List[Application]:
        """Get all applications for the current user."""
        return (
            self._user_filter(self.session.query(Application))
            .order_by(Application.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_saved_jobs(self, limit: int = 50) -> List[Job]:
        """Get saved jobs."""
        return (
            self.session.query(Job)
            .join(Application, Job.id == Application.job_id)
            .filter(Application.status == "saved")
            .filter(
                Application.user_id == self.user_id
                if self.user_id is not None
                else True
            )
            .order_by(Application.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_applied_jobs(self, limit: int = 50) -> List[Job]:
        """Get jobs applied to."""
        return (
            self.session.query(Job)
            .join(Application, Job.id == Application.job_id)
            .filter(Application.status == "applied")
            .filter(
                Application.user_id == self.user_id
                if self.user_id is not None
                else True
            )
            .order_by(Application.application_date.desc())
            .limit(limit)
            .all()
        )

    def get_interview_schedule(self, limit: int = 50) -> List[Application]:
        """Get scheduled interviews."""
        return (
            self._user_filter(
                self.session.query(Application).filter(
                    Application.status == "interview_scheduled"
                )
            )
            .limit(limit)
            .all()
        )
