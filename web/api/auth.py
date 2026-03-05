"""Google OAuth token verification and JWT issuance."""

import os
from datetime import datetime, timedelta, timezone

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "7"))
_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")


def verify_google_token(credential: str) -> dict:
    """Verify a Google ID token and return its payload.

    Raises ValueError on invalid/expired tokens.
    """
    try:
        payload = google_id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            audience=_GOOGLE_CLIENT_ID,
        )
    except Exception as exc:
        raise ValueError(f"Invalid Google token: {exc}") from exc

    if not payload.get("email_verified"):
        raise ValueError("Google account email is not verified")

    return payload


def issue_jwt(google_id: str, email: str) -> str:
    """Issue a signed JWT containing the user's Google sub claim."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": google_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(days=_EXPIRE_DAYS),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Decode and verify a JWT. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
