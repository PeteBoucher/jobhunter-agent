"""User preferences routes."""

from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends
from schemas.user import PreferencesOut, PreferencesUpdate
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from src.job_matcher import SCORING_PREFERENCE_FIELDS, mark_profile_changed
from src.models import User, UserPreferences

_JSON_FIELDS = {
    "target_titles",
    "target_industries",
    "preferred_locations",
    "preferred_countries",
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
    """Create or update job preferences.

    Only fields present in the body are written; an explicit null clears one
    (the frontend's undo relies on this to restore an unset field). When a
    field the matcher reads changes, the user's existing matches are flagged
    for a rescore by the next Lambda match phase and `rescore_scheduled` is
    set on the response.
    """
    prefs = current_user.preferences
    if not prefs:
        prefs = UserPreferences(user_id=current_user.id)
        db.add(prefs)

    scoring_changed = False
    for field, value in body.model_dump(exclude_unset=True).items():
        if field in SCORING_PREFERENCE_FIELDS and getattr(prefs, field) != value:
            scoring_changed = True
        setattr(prefs, field, value)
        if field in _JSON_FIELDS:
            flag_modified(prefs, field)

    if scoring_changed:
        mark_profile_changed(db, current_user.id)
    db.commit()
    db.refresh(prefs)
    out = PreferencesOut.model_validate(prefs)
    out.rescore_scheduled = scoring_changed
    return out
