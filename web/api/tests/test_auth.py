"""Tests for auth router: POST /auth/google, GET /auth/me."""
from unittest.mock import patch

from src.models import User

from .conftest import make_token


def _google_payload(
    sub="google-new-456",
    email="new@example.com",
    name="New User",
):
    return {"sub": sub, "email": email, "name": name, "email_verified": True}


class TestGoogleLogin:
    def test_creates_new_user_and_returns_token(self, auth_client, db_session):
        with patch(
            "routers.auth_router.verify_google_token",
            return_value=_google_payload(),
        ):
            resp = auth_client.post("/auth/google", json={"id_token": "fake-token"})

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "new@example.com"
        assert data["user"]["name"] == "New User"

    def test_new_user_is_persisted_in_db(self, auth_client, db_session):
        with patch(
            "routers.auth_router.verify_google_token",
            return_value=_google_payload(
                sub="google-persist", email="persist@example.com"
            ),
        ):
            auth_client.post("/auth/google", json={"id_token": "fake-token"})

        user = (
            db_session.query(User).filter(User.email == "persist@example.com").first()
        )
        assert user is not None
        assert user.google_id == "google-persist"

    def test_returning_user_does_not_create_duplicate(self, auth_client, db_session):
        payload = _google_payload()
        with patch("routers.auth_router.verify_google_token", return_value=payload):
            auth_client.post("/auth/google", json={"id_token": "fake-token"})
            auth_client.post("/auth/google", json={"id_token": "fake-token"})

        count = db_session.query(User).filter(User.google_id == payload["sub"]).count()
        assert count == 1

    def test_invalid_google_token_returns_401(self, auth_client):
        with patch(
            "routers.auth_router.verify_google_token",
            side_effect=ValueError("Token signature is invalid"),
        ):
            resp = auth_client.post("/auth/google", json={"id_token": "bad-token"})

        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()


class TestGetMe:
    def test_returns_current_user_via_dependency_override(self, client, test_user):
        resp = client.get("/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == test_user.email
        assert data["name"] == test_user.name

    def test_no_auth_header_returns_4xx(self, auth_client):
        resp = auth_client.get("/auth/me")
        assert resp.status_code in (401, 403)

    def test_valid_jwt_resolves_correct_user(self, auth_client, db_session):
        """End-to-end: a real JWT decodes to the right user without mocking."""
        user = User(
            google_id="google-real-789",
            email="real@example.com",
            name="Real User",
            is_approved=True,
        )
        db_session.add(user)
        db_session.commit()

        token = make_token(user)
        resp = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "real@example.com"

    def test_tampered_jwt_returns_401(self, auth_client):
        resp = auth_client.get(
            "/auth/me", headers={"Authorization": "Bearer not.a.real.jwt"}
        )
        assert resp.status_code == 401
