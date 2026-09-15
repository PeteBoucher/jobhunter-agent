"""Tests for user "not interested" job rejections."""

import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.job_rejections import (
    get_rejected_job_ids,
    get_rejected_jobs,
    reject_job,
    unreject_job,
)
from src.models import Base, Job, User


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


def _job(session, title="Backend Engineer", company="Acme"):
    job = Job(title=title, company=company, source="test")
    session.add(job)
    session.commit()
    return job


def _user(session, name="Alice"):
    user = User(name=name)
    session.add(user)
    session.commit()
    return user


def test_reject_job(session):
    user = _user(session)
    job = _job(session)

    row = reject_job(session, user.id, job.id, reason="wrong location")
    assert row.job_id == job.id
    assert row.user_id == user.id
    assert row.reason == "wrong location"


def test_reject_job_is_idempotent(session):
    """Rejecting the same job twice updates the reason, not a duplicate row."""
    user = _user(session)
    job = _job(session)

    row1 = reject_job(session, user.id, job.id, reason="first reason")
    row2 = reject_job(session, user.id, job.id, reason="updated reason")

    assert row1.id == row2.id
    assert row2.reason == "updated reason"
    assert len(get_rejected_job_ids(session, user.id)) == 1


def test_reject_job_without_reason_keeps_none(session):
    user = _user(session)
    job = _job(session)

    row = reject_job(session, user.id, job.id)
    assert row.reason is None


def test_unreject_job_removes_row(session):
    user = _user(session)
    job = _job(session)
    reject_job(session, user.id, job.id)

    assert unreject_job(session, user.id, job.id) is True
    assert get_rejected_job_ids(session, user.id) == set()


def test_unreject_job_no_op_when_not_rejected(session):
    user = _user(session)
    job = _job(session)

    assert unreject_job(session, user.id, job.id) is False


def test_get_rejected_jobs_scoped_per_user(session):
    user_a = _user(session, "Alice")
    user_b = _user(session, "Bob")
    job = _job(session)

    reject_job(session, user_a.id, job.id)

    assert [j.id for j in get_rejected_jobs(session, user_a.id)] == [job.id]
    assert get_rejected_jobs(session, user_b.id) == []


def test_get_rejected_jobs_newest_first(session):
    user = _user(session)
    job1 = _job(session, title="First")
    job2 = _job(session, title="Second")

    reject_job(session, user.id, job1.id)
    reject_job(session, user.id, job2.id)

    rejected = get_rejected_jobs(session, user.id)
    assert [j.id for j in rejected] == [job2.id, job1.id]


def test_legacy_single_user_mode_ignores_user_scoping(session):
    """user_id=None mirrors ApplicationTracker's legacy CLI mode: unscoped."""
    job = _job(session)

    reject_job(session, None, job.id, reason="cli reject")
    assert unreject_job(session, None, job.id) is True


# ---------------------------------------------------------------------------
# CLI (`job-agent jobs reject/unreject/list-rejected`)
# ---------------------------------------------------------------------------


def test_jobs_group_keeps_all_subcommands():
    """Regression guard: `jobs` is a single pre-existing CLI group (search/view/
    recent) — reject/unreject/list-rejected must be added to it, not redefined
    as a second `@cli.group() def jobs()`, which would silently shadow the
    first and drop its commands from the CLI (mypy's `no-redef` catches this
    at typecheck time, but nothing at runtime does)."""
    from src.cli import cli

    subcommands = set(cli.commands["jobs"].commands.keys())
    assert {"search", "view", "recent", "reject", "unreject", "list-rejected"} <= (
        subcommands
    )


def test_cli_reject_and_unreject(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from src.cli import cli
    from src.database import get_session, init_db

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    init_db()
    session = get_session()
    job = _job(session)
    job_id, job_title = job.id, job.title
    session.close()

    runner = CliRunner()
    result = runner.invoke(
        cli, ["jobs", "reject", str(job_id), "--reason", "not remote"]
    )
    assert result.exit_code == 0, result.output
    assert "Rejected" in result.output

    result = runner.invoke(cli, ["jobs", "list-rejected"])
    assert result.exit_code == 0, result.output
    assert job_title in result.output

    result = runner.invoke(cli, ["jobs", "unreject", str(job_id)])
    assert result.exit_code == 0, result.output
    assert "Un-rejected" in result.output
