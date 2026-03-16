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
    engine = create_engine_instance()
    session_factory = sessionmaker(bind=engine)
    return session_factory()


def create_engine_instance():
    """Create and return SQLAlchemy engine."""
    url = get_database_url()
    kwargs: dict = {"echo": False}
    if url.startswith("postgresql"):
        # Neon serverless drops idle connections after ~5 min.
        # pool_pre_ping checks connections on checkout.
        # TCP keepalives prevent the SSL link going stale mid-session
        # (e.g. while _fetch_jobs() makes slow HTTP calls).
        kwargs.update(
            {
                "pool_pre_ping": True,
                "pool_size": 5,
                "max_overflow": 10,
                "connect_args": {
                    "keepalives": 1,
                    "keepalives_idle": 60,
                    "keepalives_interval": 10,
                    "keepalives_count": 5,
                },
            }
        )
    return create_engine(url, **kwargs)
