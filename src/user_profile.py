"""User profile management module."""

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from src.cv_parser import parse_cv_file
from src.models import User, UserPreferences


class UserProfile:
    """Manage user profile and preferences."""

    def __init__(self, session: Session):
        """Initialize with database session."""
        self.session = session

    def create_profile_from_cv(
        self,
        cv_file_path: str,
        target_titles: Optional[List[str]] = None,
        target_industries: Optional[List[str]] = None,
        preferred_locations: Optional[List[str]] = None,
        salary_min: Optional[float] = None,
        salary_max: Optional[float] = None,
        experience_level: Optional[str] = None,
        remote_preference: Optional[str] = None,
        contract_types: Optional[List[str]] = None,
    ) -> User:
        """Create user profile from CV file with optional preferences.

        Args:
            cv_file_path: Path to CV markdown file
            target_titles: List of target job titles
            target_industries: List of target industries
            preferred_locations: List of preferred job locations
            salary_min: Minimum desired salary
            salary_max: Maximum desired salary
            experience_level: Junior, Mid, Senior, Lead
            remote_preference: onsite, hybrid, remote
            contract_types: Full-time, Part-time, Contract

        Returns:
            Created or updated User object

        Raises:
            FileNotFoundError: If CV file not found
            ValueError: If CV parsing fails or required data missing
        """
        # Parse CV
        cv_data = parse_cv_file(cv_file_path)
        if not cv_data or not cv_data.get("personal_info", {}).get("name"):
            raise ValueError(f"Failed to parse CV from {cv_file_path}")

        personal_info = cv_data["personal_info"]
        name = personal_info.get("name")
        if not name:
            raise ValueError("CV must contain a name")

        # Check if user already exists
        user = self.session.query(User).filter_by(name=name).first()
        if user:
            # Update existing user
            user.cv_text = open(cv_file_path, "r", encoding="utf-8").read()
            user.cv_parsed_json = cv_data
            user.title = personal_info.get("title")
            user.location = personal_info.get("location")
        else:
            # Create new user
            user = User(
                name=name,
                title=personal_info.get("title"),
                location=personal_info.get("location"),
                cv_text=open(cv_file_path, "r", encoding="utf-8").read(),
                cv_parsed_json=cv_data,
            )
            self.session.add(user)
            self.session.flush()  # Get the user ID without committing yet

        # Create or update preferences
        preferences = (
            self.session.query(UserPreferences).filter_by(user_id=user.id).first()
        )

        if preferences:
            # Update existing preferences
            if target_titles is not None:
                preferences.target_titles = target_titles
            if target_industries is not None:
                preferences.target_industries = target_industries
            if preferred_locations is not None:
                preferences.preferred_locations = preferred_locations
            if salary_min is not None:
                preferences.salary_min = salary_min
            if salary_max is not None:
                preferences.salary_max = salary_max
            if experience_level is not None:
                preferences.experience_level = experience_level
            if remote_preference is not None:
                preferences.remote_preference = remote_preference
            if contract_types is not None:
                preferences.contract_types = contract_types
        else:
            # Create new preferences
            preferences = UserPreferences(
                user_id=user.id,
                target_titles=target_titles or [],
                target_industries=target_industries or [],
                preferred_locations=preferred_locations or [],
                salary_min=salary_min,
                salary_max=salary_max,
                experience_level=experience_level,
                remote_preference=remote_preference,
                contract_types=contract_types or [],
            )
            self.session.add(preferences)

        self.session.commit()
        return user

    def get_user_preferences(self, user_id: int) -> Optional[Dict]:
        """Get user preferences as dictionary.

        Args:
            user_id: User ID

        Returns:
            Dictionary of preferences or None if not found
        """
        preferences = (
            self.session.query(UserPreferences).filter_by(user_id=user_id).first()
        )
        if not preferences:
            return None

        return {
            "target_titles": preferences.target_titles or [],
            "target_industries": preferences.target_industries or [],
            "preferred_locations": preferences.preferred_locations or [],
            "salary_min": preferences.salary_min,
            "salary_max": preferences.salary_max,
            "experience_level": preferences.experience_level,
            "remote_preference": preferences.remote_preference,
            "contract_types": preferences.contract_types or [],
        }

    def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User object or None if not found
        """
        return self.session.query(User).filter_by(id=user_id).first()

    def list_users(self) -> List[User]:
        """List all users.

        Returns:
            List of User objects
        """
        return self.session.query(User).all()
