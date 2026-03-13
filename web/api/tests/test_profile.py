"""Tests for profile router: GET/PUT/DELETE /profile and DELETE /profile/skills/{id}."""
from src.models import Application, Job, JobMatch, User, UserPreferences


class TestGetProfile:
    def test_returns_user_fields(self, client, test_user):
        resp = client.get("/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name
        assert data["skills"] == []

    def test_includes_skills_when_present(self, client, db_session, test_user):
        from src.models import Skill

        skill = Skill(
            skill_name="Python", proficiency=4, category="technical", user=test_user
        )
        db_session.add(skill)
        db_session.commit()

        resp = client.get("/profile")
        assert resp.status_code == 200
        skills = resp.json()["skills"]
        assert len(skills) == 1
        assert skills[0]["skill_name"] == "Python"

    def test_unauthenticated_returns_4xx(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code in (401, 403)


class TestUpdateProfile:
    def test_updates_all_basic_fields(self, client, test_user):
        resp = client.put(
            "/profile",
            json={"name": "Alice", "title": "Staff Engineer", "location": "Berlin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Alice"
        assert data["title"] == "Staff Engineer"
        assert data["location"] == "Berlin"

    def test_partial_update_leaves_other_fields_unchanged(self, client):
        client.put("/profile", json={"name": "Alice", "title": "CTO"})
        resp = client.put("/profile", json={"location": "Dublin"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Alice"
        assert data["title"] == "CTO"
        assert data["location"] == "Dublin"

    def test_returns_updated_user_object(self, client):
        resp = client.put("/profile", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"


class TestDeleteAccount:
    def test_returns_204(self, client):
        resp = client.delete("/profile")
        assert resp.status_code == 204
        assert resp.content == b""

    def test_user_is_removed_from_db(self, client, db_session, test_user):
        user_id = test_user.id
        client.delete("/profile")
        remaining = db_session.query(User).filter(User.id == user_id).first()
        assert remaining is None

    def test_cascades_to_applications(self, client, db_session, test_user):
        job = Job(title="Dev", company="Acme", source="test")
        db_session.add(job)
        db_session.commit()

        app = Application(job_id=job.id, user_id=test_user.id, status="saved")
        db_session.add(app)
        db_session.commit()

        client.delete("/profile")

        remaining = (
            db_session.query(Application)
            .filter(Application.user_id == test_user.id)
            .count()
        )
        assert remaining == 0

    def test_cascades_to_job_matches(self, client, db_session, test_user):
        job = Job(title="Dev", company="Acme", source="test")
        db_session.add(job)
        db_session.commit()

        match = JobMatch(job_id=job.id, user_id=test_user.id, match_score=80.0)
        db_session.add(match)
        db_session.commit()

        client.delete("/profile")

        remaining = (
            db_session.query(JobMatch).filter(JobMatch.user_id == test_user.id).count()
        )
        assert remaining == 0

    def test_cascades_to_preferences(self, client, db_session, test_user):
        prefs = UserPreferences(user_id=test_user.id, salary_min=80000)
        db_session.add(prefs)
        db_session.commit()

        client.delete("/profile")

        remaining = (
            db_session.query(UserPreferences)
            .filter(UserPreferences.user_id == test_user.id)
            .count()
        )
        assert remaining == 0

    def test_does_not_delete_other_users(
        self, client, db_session, test_user
    ):  # noqa: E501
        other = User(
            google_id="other-999", email="other@example.com", name="Other User"
        )
        db_session.add(other)
        db_session.commit()
        other_id = other.id

        client.delete("/profile")

        still_there = db_session.query(User).filter(User.id == other_id).first()
        assert still_there is not None


class TestDeleteSkill:
    def _add_skill(self, db_session, user, name="Python"):
        from src.models import Skill

        skill = Skill(skill_name=name, proficiency=4, category="technical", user=user)
        db_session.add(skill)
        db_session.commit()
        db_session.refresh(skill)
        return skill

    def test_removes_skill_from_db(self, client, db_session, test_user):
        skill = self._add_skill(db_session, test_user)
        resp = client.delete(f"/profile/skills/{skill.id}")
        assert resp.status_code == 204
        from src.models import Skill

        assert db_session.query(Skill).filter_by(id=skill.id).first() is None

    def test_returns_204_no_body(self, client, db_session, test_user):
        skill = self._add_skill(db_session, test_user)
        resp = client.delete(f"/profile/skills/{skill.id}")
        assert resp.status_code == 204
        assert resp.content == b""

    def test_returns_404_for_unknown_skill(self, client):
        resp = client.delete("/profile/skills/99999")
        assert resp.status_code == 404

    def test_cannot_delete_another_users_skill(self, client, db_session):
        other = User(google_id="other-888", email="other2@example.com", name="Other")
        db_session.add(other)
        db_session.commit()
        skill = self._add_skill(db_session, other, name="Go")
        resp = client.delete(f"/profile/skills/{skill.id}")
        assert resp.status_code == 404  # not leaked as 403

    def test_only_target_skill_removed(self, client, db_session, test_user):
        """Deleting one skill leaves sibling skills untouched."""
        from src.models import Skill

        s1 = self._add_skill(db_session, test_user, name="Python")
        s2 = self._add_skill(db_session, test_user, name="SQL")
        client.delete(f"/profile/skills/{s1.id}")
        assert db_session.query(Skill).filter_by(id=s2.id).first() is not None

    def test_profile_reflects_removal(self, client, db_session, test_user):
        """GET /profile after deletion no longer includes the removed skill."""
        skill = self._add_skill(db_session, test_user, name="Kubernetes")
        client.delete(f"/profile/skills/{skill.id}")
        resp = client.get("/profile")
        skill_names = [s["skill_name"] for s in resp.json()["skills"]]
        assert "Kubernetes" not in skill_names

    def test_requires_authentication(self, auth_client):
        resp = auth_client.delete("/profile/skills/1")
        assert resp.status_code in (401, 403)
