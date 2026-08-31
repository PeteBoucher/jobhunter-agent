"""Tests for application tracking functionality."""

import tempfile
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application_tracker import (
    ApplicationTracker,
    archive_applications_for_inactive_jobs,
)
from src.models import Application, Base, Job


@pytest.fixture
def session():
    """Create a test database session."""
    db_fd, db_path = tempfile.mkstemp()
    database_url = f"sqlite:///{db_path}"

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()
    import os

    os.close(db_fd)
    os.unlink(db_path)


def test_save_job(session):
    """Test saving a job for later."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Test Job",
        company="TestCorp",
    )
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    app = tracker.save_job(job.id, notes="Interesting opportunity")

    assert app.status == "saved"
    assert app.notes == "Interesting opportunity"
    assert app.job_id == job.id


def test_apply_to_job(session):
    """Test recording an application."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Test Job",
        company="TestCorp",
    )
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    app = tracker.apply_to_job(job.id, notes="Applied on LinkedIn")

    assert app.status == "applied"
    assert app.application_date is not None
    assert app.notes == "Applied on LinkedIn"


def test_get_application(session):
    """Test retrieving an application."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Test Job",
        company="TestCorp",
    )
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    tracker.apply_to_job(job.id)

    app = tracker.get_application(job.id)
    assert app is not None
    assert app.status == "applied"


def test_get_applications_by_status(session):
    """Test retrieving applications by status."""
    # Create jobs
    job1 = Job(source="test", source_job_id="1", title="Job 1", company="Corp1")
    job2 = Job(source="test", source_job_id="2", title="Job 2", company="Corp2")
    session.add(job1)
    session.add(job2)
    session.commit()

    tracker = ApplicationTracker(session)
    tracker.apply_to_job(job1.id)
    tracker.save_job(job2.id)

    applied = tracker.get_applications_by_status("applied")
    assert len(applied) == 1

    saved = tracker.get_applications_by_status("saved")
    assert len(saved) == 1


def test_reject_application(session):
    """Test rejecting an application."""
    job = Job(source="test", source_job_id="1", title="Test Job", company="Corp")
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    app = tracker.reject_application(job.id, reason="Not a good fit")

    assert app.status == "rejected"
    # Note: rejection_reason is not in the basic Application model
    # so we use the notes field instead via our implementation


def test_offer_received(session):
    """Test marking an offer as received."""
    job = Job(source="test", source_job_id="1", title="Test Job", company="Corp")
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    app = tracker.offer_received(job.id, notes="Offer $120k/year")

    assert app.status == "offer"
    assert app.notes == "Offer $120k/year"


def test_archive_applications_for_inactive_jobs_archives_expired(session):
    """An application linked to an inactive job gets archived."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Old Job",
        company="Corp",
        is_active=False,
    )
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    app = tracker.save_job(job.id)

    count = archive_applications_for_inactive_jobs(session)

    assert count == 1
    session.refresh(app)
    assert app.archived is True
    assert app.archived_at is not None


def test_archive_applications_for_inactive_jobs_skips_active_jobs(session):
    """An application linked to a still-active job is left alone."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Fresh Job",
        company="Corp",
        is_active=True,
    )
    session.add(job)
    session.commit()

    tracker = ApplicationTracker(session)
    app = tracker.save_job(job.id)

    count = archive_applications_for_inactive_jobs(session)

    assert count == 0
    session.refresh(app)
    assert app.archived is False


def test_archive_applications_for_inactive_jobs_skips_already_archived(session):
    """Applications already archived are not re-counted or re-stamped."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Old Job",
        company="Corp",
        is_active=False,
    )
    session.add(job)
    session.commit()

    original_ts = datetime(2020, 1, 1)
    app = Application(
        job_id=job.id, status="saved", archived=True, archived_at=original_ts
    )
    session.add(app)
    session.commit()

    count = archive_applications_for_inactive_jobs(session)

    assert count == 0
    session.refresh(app)
    assert app.archived_at == original_ts


def test_archive_applications_for_inactive_jobs_covers_all_statuses(session):
    """Archiving applies regardless of application status (offer, rejected, etc.)."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Old Job",
        company="Corp",
        is_active=False,
    )
    session.add(job)
    session.commit()

    app = Application(job_id=job.id, status="offer")
    session.add(app)
    session.commit()

    count = archive_applications_for_inactive_jobs(session)

    assert count == 1
    session.refresh(app)
    assert app.archived is True


def test_get_all_applications_excludes_archived(session):
    """Archived applications are hidden from the default kanban listing."""
    active_job = Job(
        source="test",
        source_job_id="1",
        title="Fresh Job",
        company="Corp",
        is_active=True,
    )
    stale_job = Job(
        source="test",
        source_job_id="2",
        title="Old Job",
        company="Corp",
        is_active=False,
    )
    session.add_all([active_job, stale_job])
    session.commit()

    tracker = ApplicationTracker(session)
    tracker.save_job(active_job.id)
    tracker.save_job(stale_job.id)
    archive_applications_for_inactive_jobs(session)

    apps = tracker.get_all_applications()
    assert len(apps) == 1
    assert apps[0].job_id == active_job.id
