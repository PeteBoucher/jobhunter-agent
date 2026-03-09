import pytest

from src.database import get_session, init_db
from src.job_matcher import compute_match_for_user
from src.models import Job, Skill, User, UserPreferences


@pytest.fixture(autouse=True)
def session_tmp(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    init_db()
    session = get_session()
    yield session
    session.close()


def test_basic_match(session_tmp):
    session = session_tmp
    # create user, preferences, skill
    user = User(name="Alice")
    prefs = UserPreferences(
        experience_level="mid",
        remote_preference="remote",
        preferred_locations=["New York"],
        salary_min=90000,
        target_titles=["Software Engineer", "Backend Engineer"],
    )
    user.preferences = prefs
    skill = Skill(skill_name="python", proficiency=8, user=user)
    session.add(user)
    session.add(skill)
    session.commit()

    job = Job(
        title="Senior Backend Engineer",
        company="Acme",
        location="Remote",
        remote="remote",
        salary_min=120000,
        requirements=["Python", "Django", "APIs"],
    )
    session.add(job)
    session.commit()

    jm = compute_match_for_user(session, job, user)
    assert jm.match_score > 0
    assert jm.user_id == user.id
    assert jm.job_id == job.id


def test_upsert_does_not_create_duplicate_rows(session_tmp):
    """Calling compute_match_for_user twice must update the row, not insert a new one.

    This is a regression test for the bug where 0-score rows from the Lambda's
    first run persisted because every call inserted instead of upserted.
    """
    session = session_tmp
    user = User(name="Bob")
    session.add(user)
    session.commit()

    job = Job(title="Engineer", company="Co", source="test")
    session.add(job)
    session.commit()

    from src.models import JobMatch

    jm1 = compute_match_for_user(session, job, user)
    first_id = jm1.id

    # Second call — must reuse the same row
    jm2 = compute_match_for_user(session, job, user)
    assert jm2.id == first_id

    count = (
        session.query(JobMatch)
        .filter(JobMatch.job_id == job.id, JobMatch.user_id == user.id)
        .count()
    )
    assert count == 1


def test_upsert_updates_score_on_second_call(session_tmp):
    """Score is refreshed on subsequent calls (e.g. after a CV update)."""
    session = session_tmp

    user = User(name="Carol")
    prefs = UserPreferences(
        target_titles=["Engineer"],
        remote_preference="remote",
    )
    user.preferences = prefs
    session.add(user)
    session.commit()

    job = Job(
        title="Backend Engineer",
        company="Co",
        source="test",
        remote="remote",
        requirements=["Python", "SQL"],
    )
    session.add(job)
    session.commit()

    # First call — no skills yet, score will be low
    jm1 = compute_match_for_user(session, job, user)
    first_score = jm1.match_score

    # Add a skill that matches the job requirements
    skill = Skill(skill_name="python", proficiency=5, user=user)
    session.add(skill)
    session.commit()

    # Expire the user so SQLAlchemy reloads the skills relationship
    session.expire(user)

    jm2 = compute_match_for_user(session, job, user)
    # Score must have increased and still only one row
    assert jm2.match_score > first_score
    from src.models import JobMatch

    assert (
        session.query(JobMatch)
        .filter(JobMatch.job_id == job.id, JobMatch.user_id == user.id)
        .count()
        == 1
    )


def test_match_cli_invocation(session_tmp, capsys):
    # Sanity run of CLI match command to ensure it runs without error
    from click.testing import CliRunner

    from src.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["match"])
    assert result.exit_code == 0
