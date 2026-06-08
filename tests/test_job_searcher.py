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


# ── Regression: onsite remote filter ─────────────────────────────────────────
# Bug: remote=onsite required Job.remote == "onsite" but onsite jobs almost
# always have remote=NULL — they never appeared in the feed.


def test_onsite_filter_includes_null_remote_jobs(session):
    """Jobs with remote=NULL must appear when filtering remote=onsite."""
    session.add_all(
        [
            Job(
                source="t",
                source_job_id="1",
                title="Office Job",
                company="A",
                remote=None,
            ),
            Job(
                source="t",
                source_job_id="2",
                title="Remote Job",
                company="B",
                remote="remote",
            ),
        ]
    )
    session.commit()

    results = JobSearcher(session).search(remote="onsite")
    titles = {j.title for j in results}
    assert "Office Job" in titles
    assert "Remote Job" not in titles


def test_onsite_filter_excludes_remote_and_hybrid(session):
    """remote=onsite must exclude jobs explicitly tagged remote or hybrid."""
    session.add_all(
        [
            Job(
                source="t",
                source_job_id="1",
                title="Onsite Tagged",
                company="A",
                remote="onsite",
            ),
            Job(
                source="t",
                source_job_id="2",
                title="Null Remote",
                company="B",
                remote=None,
            ),
            Job(
                source="t",
                source_job_id="3",
                title="Hybrid Job",
                company="C",
                remote="hybrid",
            ),
            Job(
                source="t",
                source_job_id="4",
                title="Remote Job",
                company="D",
                remote="remote",
            ),
        ]
    )
    session.commit()

    results = JobSearcher(session).search(remote="onsite")
    titles = {j.title for j in results}
    assert "Onsite Tagged" in titles
    assert "Null Remote" in titles
    assert "Hybrid Job" not in titles
    assert "Remote Job" not in titles


# ── Regression: location list filter ─────────────────────────────────────────
# Bug: location fallback in the router passed only preferred_locations[0],
# silently dropping every other preferred location.


def test_location_filter_accepts_list_and_ors_them(session):
    """Passing a list of locations returns jobs matching ANY of them."""
    session.add_all(
        [
            Job(
                source="t",
                source_job_id="1",
                title="Malaga Job",
                company="A",
                location="Malaga",
            ),
            Job(
                source="t",
                source_job_id="2",
                title="Gibraltar Job",
                company="B",
                location="Gibraltar",
            ),
            Job(
                source="t",
                source_job_id="3",
                title="Berlin Job",
                company="C",
                location="Berlin",
            ),
        ]
    )
    session.commit()

    results = JobSearcher(session).search(location=["Malaga", "Gibraltar"])
    titles = {j.title for j in results}
    assert "Malaga Job" in titles
    assert "Gibraltar Job" in titles
    assert "Berlin Job" not in titles
