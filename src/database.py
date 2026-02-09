"""Database initialization and session management."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.models import Base


def get_database_url() -> str:
    """Get database URL from environment or use SQLite default."""
    return os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")


def init_db() -> None:
    """Initialize database schema."""
    engine = create_engine(get_database_url(), echo=False)
    Base.metadata.create_all(engine)
    print(f"✓ Database initialized at {get_database_url()}")


def get_session() -> Session:
    """Get a new database session."""
    engine = create_engine(get_database_url())
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def create_engine_instance():
    """Create and return SQLAlchemy engine."""
    return create_engine(get_database_url(), echo=False)
