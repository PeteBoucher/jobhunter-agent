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


def test_match_cli_invocation(session_tmp, capsys):
    # Sanity run of CLI match command to ensure it runs without error
    from click.testing import CliRunner

    from src.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["match"])
    assert result.exit_code == 0
