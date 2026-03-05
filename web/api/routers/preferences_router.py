"""User preferences routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.models import User, UserPreferences

from ..dependencies import get_current_user, get_db
from ..schemas.user import PreferencesOut, PreferencesUpdate

router = APIRouter(prefix="/preferences", tags=["preferences"])


@router.get("", response_model=PreferencesOut)
def get_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's job preferences."""
    prefs = current_user.preferences
    if not prefs:
        return PreferencesOut()
    return PreferencesOut.model_validate(prefs)


@router.put("", response_model=PreferencesOut)
def update_preferences(
    body: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create or update job preferences."""
    prefs = current_user.preferences
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(prefs, field, value)

    db.commit()
    db.refresh(prefs)
    return PreferencesOut.model_validate(prefs)
