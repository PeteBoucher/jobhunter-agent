"""Authentication routes: Google OAuth → JWT."""

from auth import issue_jwt, verify_google_token
from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from schemas.user import UserOut
from sqlalchemy.orm import Session

from src.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


@router.post("/google", response_model=TokenResponse)
def google_login(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Exchange a Google ID token for a jobhunter JWT."""
    try:
        payload = verify_google_token(body.id_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    google_id: str = payload["sub"]
    email: str = payload.get("email", "")
    name: str = payload.get("name", "")

    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        # Auto-create on first login
        user = User(google_id=google_id, email=email, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = issue_jwt(google_id, email)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user."""
    return UserOut.model_validate(current_user)
