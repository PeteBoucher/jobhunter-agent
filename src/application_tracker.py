"""Job application tracking functionality."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models import Application, Job


class ApplicationTracker:
    """Track job applications."""

    def __init__(self, session: Session):
        """Initialize application tracker.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def save_job(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Save a job for later.

        Args:
            job_id: ID of the job to save
            notes: Optional notes about the job

        Returns:
            Application record
        """
        # Check if already saved
        existing = (
            self.session.query(Application)
            .filter(
                Application.job_id == job_id,
                Application.status == "saved",
            )
            .first()
        )
        if existing:
            return existing

        app = Application(
            job_id=job_id,
            status="saved",
            notes=notes,
        )
        self.session.add(app)
        self.session.commit()
        return app

    def apply_to_job(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Record an application to a job.

        Args:
            job_id: ID of the job
            notes: Optional notes about the application

        Returns:
            Application record
        """
        # Check if already applied
        existing = (
            self.session.query(Application)
            .filter(Application.job_id == job_id)
            .filter(Application.status != "saved")
            .first()
        )
        if existing:
            existing.status = "applied"
            existing.application_date = datetime.utcnow()
            existing.notes = notes
            self.session.commit()
            return existing

        app = Application(
            job_id=job_id,
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
        """Schedule an interview for a job.

        Args:
            job_id: ID of the job
            interview_date: Date/time of the interview
            notes: Optional notes about the interview

        Returns:
            Application record
        """
        app = (
            self.session.query(Application).filter(Application.job_id == job_id).first()
        )
        if not app:
            app = Application(job_id=job_id)
            self.session.add(app)

        app.status = "interview_scheduled"
        if notes:
            app.notes = notes
        self.session.commit()
        return app

    def mark_interviewed(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Mark a job as interviewed.

        Args:
            job_id: ID of the job
            notes: Optional notes about the interview

        Returns:
            Application record
        """
        app = (
            self.session.query(Application).filter(Application.job_id == job_id).first()
        )
        if not app:
            app = Application(job_id=job_id)
            self.session.add(app)

        app.status = "interviewed"
        if notes:
            app.notes = notes
        self.session.commit()
        return app

    def reject_application(
        self, job_id: int, reason: Optional[str] = None
    ) -> Application:
        """Mark an application as rejected.

        Args:
            job_id: ID of the job
            reason: Reason for rejection

        Returns:
            Application record
        """
        app = (
            self.session.query(Application).filter(Application.job_id == job_id).first()
        )
        if not app:
            app = Application(job_id=job_id)
            self.session.add(app)

        app.status = "rejected"
        app.notes = reason if reason else app.notes
        self.session.commit()
        return app

    def offer_received(self, job_id: int, notes: Optional[str] = None) -> Application:
        """Mark that an offer was received for a job.

        Args:
            job_id: ID of the job
            notes: Optional notes about the offer

        Returns:
            Application record
        """
        app = (
            self.session.query(Application).filter(Application.job_id == job_id).first()
        )
        if not app:
            app = Application(job_id=job_id)
            self.session.add(app)

        app.status = "offer"
        if notes:
            app.notes = notes
        self.session.commit()
        return app

    def get_application(self, job_id: int) -> Optional[Application]:
        """Get application record for a job.

        Args:
            job_id: ID of the job

        Returns:
            Application record or None
        """
        return (
            self.session.query(Application).filter(Application.job_id == job_id).first()
        )

    def get_applications_by_status(
        self, status: str, limit: int = 50
    ) -> List[Application]:
        """Get applications by status.

        Args:
            status: Application status to filter
            limit: Maximum number of results

        Returns:
            List of applications
        """
        return (
            self.session.query(Application)
            .filter(Application.status == status)
            .order_by(Application.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_saved_jobs(self, limit: int = 50) -> List[Job]:
        """Get saved jobs.

        Args:
            limit: Maximum number of results

        Returns:
            List of saved jobs
        """
        return (
            self.session.query(Job)
            .join(Application, Job.id == Application.job_id)
            .filter(Application.status == "saved")
            .order_by(Application.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_applied_jobs(self, limit: int = 50) -> List[Job]:
        """Get jobs applied to.

        Args:
            limit: Maximum number of results

        Returns:
            List of jobs applied to
        """
        return (
            self.session.query(Job)
            .join(Application, Job.id == Application.job_id)
            .filter(Application.status == "applied")
            .order_by(Application.application_date.desc())
            .limit(limit)
            .all()
        )

    def get_interview_schedule(self, limit: int = 50) -> List[Application]:
        """Get scheduled interviews.

        Args:
            limit: Maximum number of results

        Returns:
            List of interview applications
        """
        return (
            self.session.query(Application)
            .filter(Application.status == "interview_scheduled")
            .limit(limit)
            .all()
        )
