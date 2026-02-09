"""Tests for CLI interface."""

import os
import tempfile

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        yield db_path
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.fixture
def cli_runner():
    """Create CLI runner."""
    return CliRunner()


@pytest.fixture
def sample_cv_file(tmp_path):
    """Create a sample CV file for testing."""
    cv_content = """# John Doe

## Contact Information
- **Location**: San Francisco, CA
- **Title**: Software Engineer

---

## Professional Experience

### Tech Corp | Senior Engineer
**Location**: San Francisco, CA | **Duration**: Jan 2021 - Present

---

## Education

### Stanford University | BS
"""
    cv_file = tmp_path / "sample.md"
    cv_file.write_text(cv_content)
    return str(cv_file)


def test_cli_init(temp_db, cli_runner):
    """Test database initialization command."""
    result = cli_runner.invoke(cli, ["init"])
    assert result.exit_code == 0
    assert "initialized successfully" in result.output.lower()


def test_profile_upload(temp_db, cli_runner, sample_cv_file):
    """Test profile upload command."""
    # Initialize database first
    cli_runner.invoke(cli, ["init"])

    # Upload profile
    result = cli_runner.invoke(
        cli,
        [
            "profile",
            "upload",
            sample_cv_file,
            "--titles",
            "Software Engineer",
            "--titles",
            "Senior Engineer",
            "--industries",
            "Tech",
            "--industries",
            "Finance",
        ],
    )
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert "Profile Created" in result.output
    assert "John Doe" in result.output


def test_profile_show(temp_db, cli_runner, sample_cv_file):
    """Test profile show command."""
    # Initialize and upload
    cli_runner.invoke(cli, ["init"])
    cli_runner.invoke(
        cli,
        [
            "profile",
            "upload",
            sample_cv_file,
            "--titles",
            "Software Engineer",
        ],
    )

    # Show profile
    result = cli_runner.invoke(cli, ["profile", "show"])
    assert result.exit_code == 0
    assert "User Profile" in result.output or "John Doe" in result.output


def test_profile_list(temp_db, cli_runner, sample_cv_file):
    """Test profile list command."""
    # Initialize and upload
    cli_runner.invoke(cli, ["init"])
    cli_runner.invoke(cli, ["profile", "upload", sample_cv_file])

    # List profiles
    result = cli_runner.invoke(cli, ["profile", "list"])
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
    assert "John Doe" in result.output or "User Profiles" in result.output


def test_profile_upload_with_salary(temp_db, cli_runner, sample_cv_file):
    """Test profile upload with salary options."""
    cli_runner.invoke(cli, ["init"])

    result = cli_runner.invoke(
        cli,
        [
            "profile",
            "upload",
            sample_cv_file,
            "--salary-min",
            "100000",
            "--salary-max",
            "200000",
        ],
    )
    assert result.exit_code == 0
    assert "100,000" in result.output or "100000" in result.output


def test_profile_upload_missing_file(temp_db, cli_runner):
    """Test profile upload with missing file."""
    cli_runner.invoke(cli, ["init"])

    result = cli_runner.invoke(
        cli,
        ["profile", "upload", "/nonexistent/file.md"],
    )
    assert result.exit_code != 0


def test_profile_list_empty(temp_db, cli_runner):
    """Test profile list with no users."""
    cli_runner.invoke(cli, ["init"])

    result = cli_runner.invoke(cli, ["profile", "list"])
    # Should handle empty list gracefully
    assert result.exit_code == 0, f"Exit code {result.exit_code}: {result.output}"
