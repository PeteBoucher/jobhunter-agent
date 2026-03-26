"""Tests for job search functionality."""

import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.job_searcher import JobSearcher
from src.models import Base, Job


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


def test_job_search_by_keywords(session):
    """Test searching jobs by keywords."""
    # Create test jobs
    job1 = Job(
        source="test",
        source_job_id="1",
        title="Python Developer",
        company="TechCorp",
        location="Remote",
        description="Python and Django",
    )
    job2 = Job(
        source="test",
        source_job_id="2",
        title="JavaScript Engineer",
        company="WebCorp",
        location="San Francisco",
        description="React and Vue",
    )
    session.add(job1)
    session.add(job2)
    session.commit()

    searcher = JobSearcher(session)
    results = searcher.search(keywords="Python")

    assert len(results) == 1
    assert results[0].title == "Python Developer"


def test_job_search_by_location(session):
    """Test searching jobs by location."""
    job1 = Job(
        source="test",
        source_job_id="1",
        title="Job 1",
        company="Corp1",
        location="Remote",
    )
    job2 = Job(
        source="test",
        source_job_id="2",
        title="Job 2",
        company="Corp2",
        location="San Francisco",
    )
    session.add(job1)
    session.add(job2)
    session.commit()

    searcher = JobSearcher(session)
    results = searcher.search(location="Remote")

    assert len(results) == 1
    assert results[0].location == "Remote"


def test_get_job_by_id(session):
    """Test getting a specific job by ID."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Test Job",
        company="TestCorp",
    )
    session.add(job)
    session.commit()

    searcher = JobSearcher(session)
    found_job = searcher.get_job_by_id(job.id)

    assert found_job is not None
    assert found_job.title == "Test Job"


def test_inactive_jobs_excluded_from_search(session):
    """Jobs marked is_active=False must not appear in feed results."""
    active = Job(source="test", source_job_id="a1", title="Active Role", company="A")
    inactive = Job(
        source="test",
        source_job_id="a2",
        title="Closed Role",
        company="B",
        is_active=False,
    )
    session.add_all([active, inactive])
    session.commit()

    searcher = JobSearcher(session)
    results = searcher.search()

    titles = [j.title for j in results]
    assert "Active Role" in titles
    assert "Closed Role" not in titles


def test_search_no_results(session):
    """Test search with no results."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Test Job",
        company="TestCorp",
    )
    session.add(job)
    session.commit()

    searcher = JobSearcher(session)
    results = searcher.search(keywords="NonExistent")

    assert len(results) == 0
