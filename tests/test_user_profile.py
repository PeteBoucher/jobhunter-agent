"""Tests for user profile module."""

import tempfile
from pathlib import Path

import pytest

from src.database import get_session, init_db
from src.user_profile import UserProfile


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        import os

        db_path = os.path.join(temp_dir, "test.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        yield db_path
        if os.path.exists(db_path):
            os.remove(db_path)


@pytest.fixture
def sample_cv_file(tmp_path):
    """Create a sample CV file for testing."""
    cv_content = """# John Doe

## Contact Information
- **Location**: San Francisco, CA
- **Email**: john@example.com
- **Phone**: (555) 123-4567
- **Title**: Software Engineer

---

## Professional Summary

Experienced software engineer with 5 years of experience building scalable systems.

---

## Professional Experience

### Tech Corp | Senior Software Engineer
**Location**: San Francisco, CA | **Duration**: Jan 2021 - Present

- Led team of 5 engineers
- Improved system performance by 40%

### StartUp Inc | Software Engineer
**Location**: San Francisco, CA | **Duration**: Jan 2019 - Dec 2020

- Built microservices using Python and Go
- Implemented CI/CD pipelines

---

## Education

### Stanford University | BS Computer Science
**Location**: Stanford, CA | **Duration**: 2015 - 2019

- GPA: 3.8
- Dean's List

---

## Languages

- English (Fluent)
- Spanish (Conversational)
"""
    cv_file = tmp_path / "sample_cv.md"
    cv_file.write_text(cv_content)
    return str(cv_file)


def test_create_profile_from_cv(temp_db, sample_cv_file):
    """Test creating user profile from CV file."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    user = profile_mgr.create_profile_from_cv(
        cv_file_path=sample_cv_file,
        target_titles=["Software Engineer", "Senior Engineer"],
        target_industries=["Tech", "Finance"],
        preferred_locations=["San Francisco", "New York"],
        salary_min=100000,
        salary_max=200000,
        experience_level="Senior",
        remote_preference="hybrid",
        contract_types=["Full-time"],
    )

    assert user.name == "John Doe"
    assert user.title == "Software Engineer"
    assert user.location == "San Francisco, CA"
    assert user.cv_text is not None
    assert user.cv_parsed_json is not None

    session.close()


def test_create_profile_preferences(temp_db, sample_cv_file):
    """Test that preferences are created with profile."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    user = profile_mgr.create_profile_from_cv(
        cv_file_path=sample_cv_file,
        target_titles=["Software Engineer"],
        target_industries=["Tech"],
        preferred_locations=["San Francisco"],
        salary_min=100000,
        salary_max=200000,
        experience_level="Senior",
        remote_preference="hybrid",
    )

    prefs = profile_mgr.get_user_preferences(user.id)
    assert prefs is not None
    assert "Software Engineer" in prefs["target_titles"]
    assert "Tech" in prefs["target_industries"]
    assert "San Francisco" in prefs["preferred_locations"]
    assert prefs["salary_min"] == 100000
    assert prefs["salary_max"] == 200000
    assert prefs["experience_level"] == "Senior"
    assert prefs["remote_preference"] == "hybrid"

    session.close()


def test_update_existing_profile(temp_db, sample_cv_file):
    """Test updating an existing user profile."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    # Create initial profile
    user1 = profile_mgr.create_profile_from_cv(
        cv_file_path=sample_cv_file,
        target_titles=["Engineer"],
    )

    user_id = user1.id

    # Update profile with new preferences
    user2 = profile_mgr.create_profile_from_cv(
        cv_file_path=sample_cv_file,
        target_titles=["Senior Engineer", "Staff Engineer"],
        target_industries=["Tech", "Finance"],
    )

    # Should be the same user
    assert user2.id == user_id

    # Check updated preferences
    prefs = profile_mgr.get_user_preferences(user_id)
    assert len(prefs["target_titles"]) == 2
    assert "Senior Engineer" in prefs["target_titles"]

    session.close()


def test_get_user(temp_db, sample_cv_file):
    """Test retrieving user by ID."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    user = profile_mgr.create_profile_from_cv(
        cv_file_path=sample_cv_file,
    )

    retrieved = profile_mgr.get_user(user.id)
    assert retrieved is not None
    assert retrieved.name == user.name
    assert retrieved.id == user.id

    session.close()


def test_get_nonexistent_user(temp_db):
    """Test retrieving non-existent user."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    user = profile_mgr.get_user(9999)
    assert user is None

    session.close()


def test_list_users(temp_db, sample_cv_file):
    """Test listing all users."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    # Create multiple users by modifying CV
    cv_content = """# Jane Doe

## Contact Information
- **Title**: Product Manager

---

## Professional Experience

### Company | PM
"""
    temp_cv2 = Path(sample_cv_file).parent / "cv2.md"
    temp_cv2.write_text(cv_content)

    profile_mgr.create_profile_from_cv(sample_cv_file)
    profile_mgr.create_profile_from_cv(str(temp_cv2))

    users = profile_mgr.list_users()
    assert len(users) == 2
    assert any(u.name == "John Doe" for u in users)
    assert any(u.name == "Jane Doe" for u in users)

    session.close()


def test_create_profile_missing_cv_file(temp_db):
    """Test error handling for missing CV file."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    # parse_cv_file returns empty dict for missing files, which raises ValueError
    with pytest.raises(ValueError):
        profile_mgr.create_profile_from_cv("/nonexistent/cv.md")

    session.close()


def test_create_profile_invalid_cv(temp_db, tmp_path):
    """Test error handling for invalid CV file."""
    init_db()
    session = get_session()
    profile_mgr = UserProfile(session)

    # Create invalid CV (no name)
    invalid_cv = tmp_path / "invalid_cv.md"
    invalid_cv.write_text("## Some Section\nNo name header")

    with pytest.raises(ValueError):
        profile_mgr.create_profile_from_cv(str(invalid_cv))

    session.close()
