"""Tests for applications router: CRUD + user isolation."""
from src.models import Application, Job, User


def _make_job(db_session, title="Dev Job", company="Acme"):
    job = Job(title=title, company=company, source="test")
    db_session.add(job)
    db_session.commit()
    return job


class TestCreateApplication:
    def test_save_for_later(self, client, db_session, test_user):
        job = _make_job(db_session)
        resp = client.post("/applications", json={"job_id": job.id, "status": "saved"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "saved"
        assert data["job_id"] == job.id
        assert data["user_id"] == test_user.id

    def test_mark_as_applied(self, client, db_session):
        job = _make_job(db_session)
        resp = client.post(
            "/applications", json={"job_id": job.id, "status": "applied"}
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "applied"

    def test_application_with_notes(self, client, db_session):
        job = _make_job(db_session)
        resp = client.post(
            "/applications",
            json={"job_id": job.id, "status": "applied", "notes": "Great company"},
        )
        assert resp.status_code == 201
        assert resp.json()["notes"] == "Great company"


class TestListApplications:
    def test_returns_all_for_current_user(self, client, db_session, test_user):
        job1 = _make_job(db_session, "Job A")
        job2 = _make_job(db_session, "Job B")
        db_session.add_all(
            [
                Application(job_id=job1.id, user_id=test_user.id, status="saved"),
                Application(job_id=job2.id, user_id=test_user.id, status="applied"),
            ]
        )
        db_session.commit()

        resp = client.get("/applications")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_does_not_return_other_users_applications(
        self, client, db_session, test_user
    ):
        other = User(google_id="other-222", email="other@example.com", name="Other")
        db_session.add(other)
        db_session.commit()

        job = _make_job(db_session)
        own = Application(job_id=job.id, user_id=test_user.id, status="saved")
        theirs = Application(job_id=job.id, user_id=other.id, status="applied")
        db_session.add_all([own, theirs])
        db_session.commit()

        resp = client.get("/applications")
        assert resp.status_code == 200
        returned_ids = [a["id"] for a in resp.json()]
        assert own.id in returned_ids
        assert theirs.id not in returned_ids

    def test_filter_by_status(self, client, db_session, test_user):
        job1 = _make_job(db_session, "Saved Job")
        job2 = _make_job(db_session, "Applied Job")
        db_session.add_all(
            [
                Application(job_id=job1.id, user_id=test_user.id, status="saved"),
                Application(job_id=job2.id, user_id=test_user.id, status="applied"),
            ]
        )
        db_session.commit()

        resp = client.get("/applications?status=saved")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["status"] == "saved"

    def test_returns_empty_list_when_none(self, client):
        resp = client.get("/applications")
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateApplication:
    def test_updates_status(self, client, db_session, test_user):
        job = _make_job(db_session)
        app = Application(job_id=job.id, user_id=test_user.id, status="saved")
        db_session.add(app)
        db_session.commit()

        resp = client.patch(f"/applications/{app.id}", json={"status": "applied"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "applied"

    def test_updates_notes(self, client, db_session, test_user):
        job = _make_job(db_session)
        app = Application(job_id=job.id, user_id=test_user.id, status="applied")
        db_session.add(app)
        db_session.commit()

        resp = client.patch(
            f"/applications/{app.id}",
            json={"status": "interview_scheduled", "notes": "Phone screen booked"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "interview_scheduled"
        assert data["notes"] == "Phone screen booked"

    def test_invalid_status_returns_422(self, client, db_session, test_user):
        job = _make_job(db_session)
        app = Application(job_id=job.id, user_id=test_user.id, status="saved")
        db_session.add(app)
        db_session.commit()

        resp = client.patch(
            f"/applications/{app.id}", json={"status": "not_a_real_status"}
        )
        assert resp.status_code == 422

    def test_cannot_update_other_users_application(self, client, db_session, test_user):
        other = User(google_id="other-333", email="other2@example.com", name="Other")
        db_session.add(other)
        db_session.commit()

        job = _make_job(db_session)
        their_app = Application(job_id=job.id, user_id=other.id, status="saved")
        db_session.add(their_app)
        db_session.commit()

        resp = client.patch(f"/applications/{their_app.id}", json={"status": "applied"})
        assert resp.status_code == 404

    def test_returns_404_for_nonexistent_application(self, client):
        resp = client.patch("/applications/99999", json={"status": "applied"})
        assert resp.status_code == 404


class TestDeleteApplication:
    def test_deletes_own_application(self, client, db_session, test_user):
        job = _make_job(db_session)
        app = Application(job_id=job.id, user_id=test_user.id, status="saved")
        db_session.add(app)
        db_session.commit()
        app_id = app.id

        resp = client.delete(f"/applications/{app_id}")
        assert resp.status_code == 204
        assert (
            db_session.query(Application).filter(Application.id == app_id).first()
            is None
        )

    def test_cannot_delete_other_users_application(self, client, db_session, test_user):
        other = User(google_id="other-444", email="other3@example.com", name="Other")
        db_session.add(other)
        db_session.commit()

        job = _make_job(db_session)
        their_app = Application(job_id=job.id, user_id=other.id, status="applied")
        db_session.add(their_app)
        db_session.commit()

        resp = client.delete(f"/applications/{their_app.id}")
        assert resp.status_code == 404

        # Ensure it wasn't actually deleted
        assert (
            db_session.query(Application).filter(Application.id == their_app.id).first()
            is not None
        )

    def test_returns_404_for_nonexistent_application(self, client):
        resp = client.delete("/applications/99999")
        assert resp.status_code == 404
