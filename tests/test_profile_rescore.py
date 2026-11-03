"""Tests for rescoring existing matches after a profile change."""

import tempfile
import time
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.job_matcher import (
    compute_match_for_user,
    mark_profile_changed,
    refresh_profile_scores,
)
from src.models import Base, Job, JobMatch, User, UserPreferences


@pytest.fixture
def session():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        engine = create_engine(f"sqlite:///{f.name}")
        Base.metadata.create_all(engine)
        s = sessionmaker(bind=engine)()
        yield s
        s.close()


def _user(session, name, remote_preference):
    user = User(name=name)
    session.add(user)
    session.flush()
    session.add(
        UserPreferences(
            user_id=user.id,
            target_titles=["Backend Engineer"],
            preferred_locations=["Malaga"],
            remote_preference=remote_preference,
        )
    )
    session.commit()
    return user


def _job(session, title, remote, location, is_active=True):
    job = Job(
        title=title,
        remote=remote,
        location=location,
        company="Acme",
        source="test",
        is_active=is_active,
    )
    session.add(job)
    session.commit()
    return job


def _location_scores(session, user):
    session.expire_all()
    return {
        m.job_id: m.location_or_remote_score
        for m in session.query(JobMatch).filter(JobMatch.user_id == user.id)
    }


@pytest.fixture
def scored(session):
    """Two users on onsite, matched against a remote and a Malaga job."""
    alice = _user(session, "alice", "onsite")
    bob = _user(session, "bob", "onsite")
    remote = _job(session, "Backend Engineer", "remote", "Remote, EU")
    malaga = _job(session, "Backend Engineer", "onsite", "Malaga, Spain")
    expired = _job(session, "Backend Engineer", "remote", "Remote", is_active=False)
    for user in (alice, bob):
        for job in (remote, malaga, expired):
            compute_match_for_user(session, job, user)
    return alice, bob, remote, malaga, expired


def _switch_to_remote(session, user):
    session.get(User, user.id).preferences.remote_preference = "remote"
    mark_profile_changed(session, user.id)
    session.commit()


def test_unflagged_users_are_not_rescored(session, scored):
    assert refresh_profile_scores(session) == {}


def test_profile_change_rescores_existing_matches(session, scored):
    alice, bob, remote, malaga, expired = scored
    assert _location_scores(session, alice)[remote.id] == 0.0

    _switch_to_remote(session, alice)
    assert refresh_profile_scores(session) == {alice.id: 1}

    after = _location_scores(session, alice)
    assert after[remote.id] == 15.0
    assert after[malaga.id] == 15.0  # local onsite job still matches on location
    assert after[expired.id] == 0.0  # inactive jobs are left alone
    match = (
        session.query(JobMatch)
        .filter(JobMatch.user_id == alice.id, JobMatch.job_id == remote.id)
        .one()
    )
    assert match.match_score == pytest.approx(
        match.title_score
        + match.skill_score
        + match.experience_score
        + match.location_or_remote_score
        + match.salary_score
        - match.rejection_penalty
    )


def test_rescore_runs_once_per_change(session, scored):
    alice = scored[0]
    _switch_to_remote(session, alice)
    refresh_profile_scores(session)
    assert session.get(User, alice.id).profile_rescored_at is not None
    assert refresh_profile_scores(session) == {}


def test_change_during_rescore_is_picked_up_next_run(session, scored):
    alice = scored[0]
    _switch_to_remote(session, alice)

    def edit_mid_run():
        # Simulates the user saving again after the rescore started.
        time.sleep(0.001)
        session.query(User).filter(User.id == alice.id).update(
            {"profile_updated_at": datetime.utcnow()}, synchronize_session=False
        )
        return False

    refresh_profile_scores(session, should_stop=edit_mid_run)
    assert alice.id in refresh_profile_scores(session)


def test_other_users_scores_untouched(session, scored):
    alice, bob = scored[0], scored[1]
    bob_before = _location_scores(session, bob)

    _switch_to_remote(session, alice)
    refresh_profile_scores(session)

    assert _location_scores(session, bob) == bob_before
    assert session.get(User, bob.id).profile_rescored_at is None


def test_stopped_rescore_stays_flagged(session, scored):
    alice = scored[0]
    _switch_to_remote(session, alice)

    assert refresh_profile_scores(session, should_stop=lambda: True) == {}

    session.expire_all()
    assert session.get(User, alice.id).profile_rescored_at is None
    assert refresh_profile_scores(session) == {alice.id: 1}
