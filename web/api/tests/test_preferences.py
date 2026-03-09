"""Tests for preferences router: GET /preferences, PUT /preferences."""
from src.models import UserPreferences


class TestGetPreferences:
    def test_returns_empty_when_no_prefs_exist(self, client):
        resp = client.get("/preferences")
        assert resp.status_code == 200
        data = resp.json()
        # All fields default to None when no row exists
        assert data["target_titles"] is None
        assert data["salary_min"] is None
        assert data["remote_preference"] is None

    def test_returns_stored_preferences(self, client, db_session, test_user):
        prefs = UserPreferences(
            user_id=test_user.id,
            target_titles=["Backend Engineer", "Staff Engineer"],
            salary_min=90000.0,
            salary_max=140000.0,
            remote_preference="remote",
            experience_level="senior",
        )
        db_session.add(prefs)
        db_session.commit()

        resp = client.get("/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_titles"] == ["Backend Engineer", "Staff Engineer"]
        assert data["salary_min"] == 90000.0
        assert data["salary_max"] == 140000.0
        assert data["remote_preference"] == "remote"
        assert data["experience_level"] == "senior"

    def test_unauthenticated_returns_4xx(self, auth_client):
        resp = auth_client.get("/preferences")
        assert resp.status_code in (401, 403)


class TestUpdatePreferences:
    def test_creates_prefs_when_none_exist(self, client):
        resp = client.put(
            "/preferences",
            json={"target_titles": ["Backend Engineer"], "remote_preference": "hybrid"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_titles"] == ["Backend Engineer"]
        assert data["remote_preference"] == "hybrid"

    def test_creates_prefs_row_in_db(self, client, db_session, test_user):
        client.put("/preferences", json={"salary_min": 70000})
        prefs = (
            db_session.query(UserPreferences)
            .filter(UserPreferences.user_id == test_user.id)
            .first()
        )
        assert prefs is not None
        assert prefs.salary_min == 70000.0

    def test_updates_existing_prefs(self, client, db_session, test_user):
        prefs = UserPreferences(user_id=test_user.id, salary_min=60000.0)
        db_session.add(prefs)
        db_session.commit()

        resp = client.put(
            "/preferences",
            json={"salary_min": 90000.0, "salary_max": 150000.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["salary_min"] == 90000.0
        assert data["salary_max"] == 150000.0

    def test_partial_update_preserves_untouched_fields(self, client):
        # First set several fields
        client.put(
            "/preferences",
            json={
                "target_titles": ["Engineer"],
                "salary_min": 70000.0,
                "remote_preference": "remote",
            },
        )
        # Update only salary_max — other fields must be preserved
        resp = client.put("/preferences", json={"salary_max": 120000.0})
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_titles"] == ["Engineer"]
        assert data["salary_min"] == 70000.0
        assert data["salary_max"] == 120000.0
        assert data["remote_preference"] == "remote"

    def test_does_not_create_duplicate_prefs_row(self, client, db_session, test_user):
        client.put("/preferences", json={"salary_min": 50000})
        client.put("/preferences", json={"salary_min": 60000})

        count = (
            db_session.query(UserPreferences)
            .filter(UserPreferences.user_id == test_user.id)
            .count()
        )
        assert count == 1

    def test_list_fields_accept_arrays(self, client):
        resp = client.put(
            "/preferences",
            json={
                "preferred_locations": ["Berlin", "Remote"],
                "contract_types": ["Full-time", "Contract"],
                "target_industries": ["Tech", "Finance"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["preferred_locations"] == ["Berlin", "Remote"]
        assert data["contract_types"] == ["Full-time", "Contract"]
        assert data["target_industries"] == ["Tech", "Finance"]
