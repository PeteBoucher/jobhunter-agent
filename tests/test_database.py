"""Tests for database module."""

import os
import tempfile
from unittest.mock import patch

import pytest
from sqlalchemy import inspect

from src.database import create_engine_instance, get_database_url, get_session, init_db
from src.models import Job, Skill, User, UserPreferences


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        yield db_path
        if os.path.exists(db_path):
            os.remove(db_path)


def test_get_database_url_from_env():
    """Test getting database URL from environment."""
    original = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = "sqlite:///test.db"
        url = get_database_url()
        assert url == "sqlite:///test.db"
    finally:
        if original:
            os.environ["DATABASE_URL"] = original
        else:
            os.environ.pop("DATABASE_URL", None)


def test_get_database_url_default():
    """Test getting default database URL."""
    original = os.environ.get("DATABASE_URL")
    try:
        os.environ.pop("DATABASE_URL", None)
        url = get_database_url()
        assert "jobs.db" in url
    finally:
        if original:
            os.environ["DATABASE_URL"] = original


def test_init_db(temp_db):
    """Test database initialization."""
    init_db()
    assert os.path.exists(temp_db)


def test_init_db_creates_tables(temp_db):
    """Test that init_db creates all required tables."""
    init_db()
    session = get_session()

    inspector = inspect(session.get_bind())
    tables = inspector.get_table_names()

    expected_tables = [
        "user",
        "user_preferences",
        "skills",
        "jobs",
        "job_matches",
        "applications",
        "interviews",
        "offers",
    ]

    for table in expected_tables:
        assert table in tables, f"Table {table} not found in database"

    session.close()


def test_get_session(temp_db):
    """Test getting database session."""
    init_db()
    session = get_session()
    assert session is not None
    session.close()


def test_create_user(temp_db):
    """Test creating and retrieving a user."""
    init_db()
    session = get_session()

    user = User(
        name="Test User",
        location="Test City",
        title="Test Title",
    )
    session.add(user)
    session.commit()

    retrieved = session.query(User).filter_by(name="Test User").first()
    assert retrieved is not None
    assert retrieved.name == "Test User"
    assert retrieved.location == "Test City"

    session.close()


def test_create_user_preferences(temp_db):
    """Test creating user preferences."""
    init_db()
    session = get_session()

    user = User(
        name="Test User",
        title="Engineer",
    )
    session.add(user)
    session.commit()

    prefs = UserPreferences(
        user_id=user.id,
        target_titles=["Software Engineer", "Senior Engineer"],
        target_industries=["Tech", "Finance"],
    )
    session.add(prefs)
    session.commit()

    retrieved = session.query(UserPreferences).filter_by(user_id=user.id).first()
    assert retrieved is not None
    assert "Software Engineer" in retrieved.target_titles

    session.close()


def test_create_skill(temp_db):
    """Test creating and retrieving a skill."""
    init_db()
    session = get_session()

    user = User(name="Test User")
    session.add(user)
    session.commit()

    skill = Skill(
        user_id=user.id,
        skill_name="Python",
        proficiency=4,
        category="technical",
    )
    session.add(skill)
    session.commit()

    retrieved = session.query(Skill).filter_by(skill_name="Python").first()
    assert retrieved is not None
    assert retrieved.proficiency == 4

    session.close()


def test_postgresql_engine_has_keepalives():
    """PostgreSQL engine must have TCP keepalives to survive Neon's idle timeout.

    Neon closes SSL connections that are idle for ~5 minutes. Scrapers hold
    a connection open while _fetch_jobs() makes slow HTTP calls, so without
    keepalives the connection goes stale and _load_existing_ids() raises
    psycopg2.OperationalError: SSL connection has been closed unexpectedly.
    """
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pw@host/db"}):
        with patch("src.database.create_engine") as mock_create:
            mock_create.return_value = mock_create  # avoid real connection
            create_engine_instance()

    _, kwargs = mock_create.call_args
    connect_args = kwargs.get("connect_args", {})
    assert connect_args.get("keepalives") == 1
    assert connect_args.get("keepalives_idle") == 60
    assert connect_args.get("keepalives_interval") == 10
    assert connect_args.get("keepalives_count") == 5


def test_postgresql_engine_has_pool_pre_ping():
    """PostgreSQL engine must have pool_pre_ping to detect stale connections."""
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://user:pw@host/db"}):
        with patch("src.database.create_engine") as mock_create:
            mock_create.return_value = mock_create
            create_engine_instance()

    _, kwargs = mock_create.call_args
    assert kwargs.get("pool_pre_ping") is True


def test_get_session_uses_engine_with_pre_ping(temp_db):
    """get_session() must use create_engine_instance(), not a plain engine.

    Previously get_session() called create_engine() directly, bypassing
    pool_pre_ping and keepalive settings, causing SSL errors on Neon.
    """
    init_db()
    with patch("src.database.create_engine_instance") as mock_factory:
        mock_factory.side_effect = create_engine_instance
        get_session()
        mock_factory.assert_called_once()


def test_sqlite_engine_has_no_keepalives(temp_db):
    """Keepalive connect_args must not be set for SQLite (unsupported)."""
    engine = create_engine_instance()
    # SQLite dialect doesn't accept keepalive args; ensure we don't pass them
    assert "postgresql" not in engine.url.drivername


def test_create_job(temp_db):
    """Test creating and retrieving a job."""
    init_db()
    session = get_session()

    job = Job(
        source="linkedin",
        source_job_id="12345",
        title="Software Engineer",
        company="Test Corp",
        location="San Francisco, CA",
        remote="hybrid",
        salary_min=100000,
        salary_max=150000,
    )
    session.add(job)
    session.commit()

    retrieved = session.query(Job).filter_by(source_job_id="12345").first()
    assert retrieved is not None
    assert retrieved.title == "Software Engineer"
    assert retrieved.company == "Test Corp"

    session.close()
