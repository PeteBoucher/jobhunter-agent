"""Shared fixtures for web/api tests.

Sets up an in-memory SQLite database and overrides FastAPI dependencies so
tests never touch the real Neon database.

IMPORTANT: env vars must be set before any app modules are imported so that
module-level singletons (the SQLAlchemy engine in dependencies.py, the JWT
secret in auth.py) pick up test values.
"""
import os
import sys

# Set test values before any app module is imported.
# load_dotenv() (called in main.py) respects existing env vars by default,
# so these will not be overwritten by the real .env file.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-32-bytes!!")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")

# Add web/api/ to sys.path for absolute imports (auth, dependencies, routers, schemas)
_API_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

# Add project root to sys.path for src.* imports
_ROOT = os.path.dirname(os.path.dirname(_API_DIR))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest  # noqa: E402
from auth import issue_jwt  # noqa: E402
from dependencies import get_current_user, get_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.models import Base, User  # noqa: E402


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine shared within a single test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """SQLAlchemy session bound to the in-memory test engine."""
    SessionLocal = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture()
def test_user(db_session):
    """A pre-existing authenticated user in the test database."""
    user = User(
        google_id="google-test-123",
        email="test@example.com",
        name="Test User",
        is_approved=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def client(db_session, test_user):
    """TestClient with get_db and get_current_user overridden for the test user."""

    def override_db():
        yield db_session

    def override_user():
        return test_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(db_session):
    """TestClient with only get_db overridden — get_current_user is real.

    Use this for auth route tests where you want to test JWT decoding and
    the user-lookup dependency properly.
    """

    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db

    with TestClient(app, raise_server_exceptions=True) as c:
        yield c

    app.dependency_overrides.clear()


def make_token(user: User) -> str:
    """Issue a real signed JWT for the given user (uses test JWT_SECRET)."""
    return issue_jwt(user.google_id or "test-sub", user.email or "test@example.com")
