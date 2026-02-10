"""Tests for data export functionality."""

import csv
import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_exporter import DataExporter
from src.models import Application, Base, Job


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


def test_export_jobs_to_json(session):
    """Test exporting jobs to JSON."""
    # Create test jobs
    job1 = Job(
        source="test",
        source_job_id="1",
        title="Python Dev",
        company="TechCorp",
        location="Remote",
    )
    job2 = Job(
        source="test",
        source_job_id="2",
        title="JS Engineer",
        company="WebCorp",
        location="SF",
    )
    session.add(job1)
    session.add(job2)
    session.commit()

    exporter = DataExporter(session)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        filepath = f.name

    try:
        exporter.export_jobs_json([job1, job2], filepath)

        # Verify file contents
        with open(filepath) as f:
            data = json.load(f)

        assert len(data) == 2
        assert data[0]["title"] == "Python Dev"

    finally:
        Path(filepath).unlink()


def test_export_jobs_to_csv(session):
    """Test exporting jobs to CSV."""
    job = Job(
        source="test",
        source_job_id="1",
        title="Test Job",
        company="TestCorp",
        location="Remote",
        salary_min=100000,
        salary_max=150000,
    )
    session.add(job)
    session.commit()

    exporter = DataExporter(session)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        filepath = f.name

    try:
        exporter.export_jobs_csv([job], filepath)

        # Verify file contents
        with open(filepath) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["title"] == "Test Job"
        assert rows[0]["company"] == "TestCorp"
        assert rows[0]["salary_min"] == "100000.0"

    finally:
        Path(filepath).unlink()


def test_export_applications_to_json(session):
    """Test exporting applications to JSON."""
    # Create a job and application
    job = Job(source="test", source_job_id="1", title="Test Job", company="Corp")
    session.add(job)
    session.commit()

    app = Application(job_id=job.id, status="applied")
    session.add(app)
    session.commit()

    exporter = DataExporter(session)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        filepath = f.name

    try:
        exporter.export_applications_json([app], filepath)

        with open(filepath) as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["status"] == "applied"
        assert data[0]["job_title"] == "Test Job"

    finally:
        Path(filepath).unlink()


def test_export_empty_jobs(session):
    """Test that exporting empty jobs raises error."""
    exporter = DataExporter(session)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        filepath = f.name

    try:
        with pytest.raises(ValueError, match="No jobs to export"):
            exporter.export_jobs_json([], filepath)
    finally:
        Path(filepath).unlink()


def test_export_with_auto_format(session):
    """Test export with auto-format detection."""
    job = Job(source="test", source_job_id="1", title="Test Job", company="Corp")
    session.add(job)
    session.commit()

    exporter = DataExporter(session)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        filepath = f.name

    try:
        exporter.export_to_file([job], filepath, data_type="jobs", format="json")

        with open(filepath) as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["title"] == "Test Job"

    finally:
        Path(filepath).unlink()
