"""User profile routes: view, update, CV upload."""

import os
import sys

from dependencies import get_current_user, get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from schemas.user import UserOut, UserUpdate
from sqlalchemy.orm import Session

from src.models import Job, User, UserPreferences

# Ensure project root on path for src.* imports
_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=UserOut)
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the current user's full profile."""
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


@router.put("", response_model=UserOut)
def update_profile(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update basic profile fields (name, title, location)."""
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


def _recompute_matches(user_id: int, db_url: str) -> None:
    """Background task: recompute match scores for all jobs for a user."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from src.job_matcher import compute_match_for_user

    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return
        jobs = session.query(Job).all()
        for job in jobs:
            compute_match_for_user(session, job, user)
        session.commit()
    finally:
        session.close()


@router.post("/cv", response_model=UserOut)
async def upload_cv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a markdown CV file, extract skills/preferences, trigger re-matching."""
    content = await file.read()
    try:
        cv_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400, detail="CV must be a UTF-8 text or markdown file"
        )

    try:
        from src.cv_parser import CVParser
        from src.user_profile import UserProfile

        parsed = CVParser(cv_text).parse()

        current_user.cv_text = cv_text
        current_user.cv_parsed_json = parsed

        # Update name/title/location from CV if not set
        personal = parsed.get("personal_info", {})
        if not current_user.name and personal.get("name"):
            current_user.name = personal["name"]
        if not current_user.title and personal.get("title"):
            current_user.title = personal["title"]
        if not current_user.location and personal.get("location"):
            current_user.location = personal["location"]

        db.commit()

        # Ensure preferences row exists
        prefs = current_user.preferences
        if not prefs:
            prefs = UserPreferences(user_id=current_user.id)
            db.add(prefs)
            db.commit()

        # Sync skills and preferences
        profile_manager = UserProfile(db)
        # _sync_skills_from_cv expects the "skills" sub-dict {category: [names]}
        profile_manager._sync_skills_from_cv(current_user, parsed.get("skills", {}))
        # _auto_populate_preferences expects the full parsed CV dict
        profile_manager._auto_populate_preferences(prefs, parsed)
        db.commit()

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CV processing failed: {exc}")

    # Trigger background re-matching
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/jobs.db")
    background_tasks.add_task(_recompute_matches, current_user.id, db_url)

    db.refresh(current_user)
    return UserOut.model_validate(current_user)
