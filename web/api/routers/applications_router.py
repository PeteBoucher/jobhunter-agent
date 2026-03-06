"""Application tracking routes."""

from typing import List, Optional

from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException, Query
from schemas.application import ApplicationCreate, ApplicationOut, ApplicationUpdate
from sqlalchemy.orm import Session

from src.application_tracker import ApplicationTracker
from src.models import Application, User

router = APIRouter(prefix="/applications", tags=["applications"])

_VALID_STATUSES = {
    "saved",
    "applied",
    "interview_scheduled",
    "interviewed",
    "offer",
    "rejected",
    "withdrawn",
}


@router.get("", response_model=List[ApplicationOut])
def list_applications(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all applications for the current user, optionally filtered by status."""
    tracker = ApplicationTracker(db, user_id=current_user.id)
    if status:
        apps = tracker.get_applications_by_status(status)
    else:
        apps = tracker.get_all_applications()
    return [ApplicationOut.model_validate(a) for a in apps]


@router.post("", response_model=ApplicationOut, status_code=201)
def create_application(
    body: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record a new application (or update an existing one)."""
    tracker = ApplicationTracker(db, user_id=current_user.id)
    if body.status == "saved":
        app = tracker.save_job(body.job_id, notes=body.notes)
    else:
        app = tracker.apply_to_job(body.job_id, notes=body.notes)
    return ApplicationOut.model_validate(app)


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: int,
    body: ApplicationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an application's status and/or notes."""
    app = (
        db.query(Application)
        .filter(
            Application.id == application_id, Application.user_id == current_user.id
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    app.status = body.status
    if body.notes is not None:
        app.notes = body.notes
    db.commit()
    db.refresh(app)
    return ApplicationOut.model_validate(app)


@router.delete("/{application_id}", status_code=204)
def delete_application(
    application_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an application (withdraw)."""
    app = (
        db.query(Application)
        .filter(
            Application.id == application_id, Application.user_id == current_user.id
        )
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(app)
    db.commit()
