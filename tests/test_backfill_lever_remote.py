"""Tests for scripts/backfill_lever_remote.py."""

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.database import get_session, init_db
from src.job_scrapers.lever_scraper import LeverScraper
from src.models import Job, JobMatch, User, UserPreferences

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts/backfill_lever_remote.py"
_spec = importlib.util.spec_from_file_location("backfill_lever_remote", _SCRIPT)
assert _spec and _spec.loader
backfill_lever_remote = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(backfill_lever_remote)


@pytest.fixture
def session():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmpdir}/test.db"
        init_db()
        session = get_session()
        yield session
        session.close()


def _raw(job_id, workplace_type):
    return {
        "id": job_id,
        "text": "Backend Engineer",
        "categories": {"location": "Spain"},
        "workplaceType": workplace_type,
        "_company_slug": "testco",
    }


def _seed(session):
    """Two stale Lever rows (remote=NULL) plus one delisted, scored for one user."""
    user = User(email="a@example.com")
    user.preferences = UserPreferences(remote_preference="remote")
    session.add(user)
    jobs = [
        Job(source="lever", source_job_id=sid, title="Backend Engineer", company="T")
        for sid in ("remote-1", "hybrid-1", "delisted-1")
    ]
    session.add_all(jobs)
    session.flush()
    for job in jobs:
        session.add(
            JobMatch(
                job_id=job.id,
                user_id=user.id,
                match_score=40.0,
                title_score=25.0,
                skill_score=15.0,
                experience_score=0.0,
                location_or_remote_score=0.0,
                salary_score=0.0,
                rejection_penalty=0.0,
            )
        )
    session.commit()


def _run(session, dry_run):
    live = [_raw("remote-1", "remote"), _raw("hybrid-1", "hybrid")]
    with patch.object(LeverScraper, "_fetch_jobs", return_value=live):
        return backfill_lever_remote.backfill(session, dry_run=dry_run)


def _state(session):
    session.expire_all()
    rows = (
        session.query(Job.source_job_id, Job.remote, JobMatch.match_score)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .all()
    )
    return {sid: (remote, score) for sid, remote, score in rows}


def test_backfill_updates_remote_and_rescores(session):
    _seed(session)

    result = _run(session, dry_run=False)

    assert result == {"jobs_updated": 2, "matches_updated": 1}
    assert _state(session) == {
        # remote-preferring user gains the full 15 location points
        "remote-1": ("remote", 55.0),
        # hybrid doesn't satisfy a remote preference — remote set, score unchanged
        "hybrid-1": ("hybrid", 40.0),
        # no longer listed by Lever — left alone
        "delisted-1": (None, 40.0),
    }


def test_backfill_dry_run_writes_nothing(session):
    _seed(session)

    result = _run(session, dry_run=True)

    assert result == {"jobs_updated": 2, "matches_updated": 1}
    assert all(state == (None, 40.0) for state in _state(session).values())
