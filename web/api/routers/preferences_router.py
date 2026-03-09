"""User preferences routes."""

from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends
from schemas.user import PreferencesOut, PreferencesUpdate
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.models import User, UserPreferences

_JSON_FIELDS = {
    "target_titles",
    "target_industries",
    "preferred_locations",
    "contract_types",
}

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
        if field in _JSON_FIELDS:
            flag_modified(prefs, field)

    db.commit()
    db.refresh(prefs)
    return PreferencesOut.model_validate(prefs)
