"""AI content generation: cover letter, tailored CV, recruiter message.

Delegates to jobhunter_ai.content_generator — returns 503 if the private
package is not installed (e.g. missing GITHUB_TOKEN at build time).
"""

import logging
from typing import Literal

from dependencies import get_current_user, get_db
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.models import Job, User

logger = logging.getLogger("jobhunter.api")
router = APIRouter(prefix="/jobs", tags=["generate"])


class GenerateRequest(BaseModel):
    type: Literal["cover_letter", "tailored_cv", "recruiter_message"]


class GenerateResponse(BaseModel):
    content: str


def _job_to_dict(job: Job) -> dict:
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "requirements": job.requirements,
    }


@router.post("/{job_id}/generate", response_model=GenerateResponse)
def generate_content(
    job_id: int,
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a cover letter, tailored CV, or recruiter message for a job."""
    try:
        from jobhunter_ai import (
            generate_cover_letter,
            generate_recruiter_message,
            generate_tailored_cv,
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="AI generation is not available on this instance.",
        )

    if not current_user.cv_text:
        raise HTTPException(
            status_code=400,
            detail="Upload your CV first before generating content.",
        )

    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_dict = _job_to_dict(job)

    try:
        if body.type == "cover_letter":
            content = generate_cover_letter(current_user.cv_text, job_dict)
        elif body.type == "tailored_cv":
            content = generate_tailored_cv(current_user.cv_text, job_dict)
        else:
            content = generate_recruiter_message(current_user.cv_text, job_dict)
    except Exception as exc:
        logger.error(
            "generate_error type=%s job_id=%d user_id=%d error=%r",
            body.type,
            job_id,
            current_user.id,
            exc,
        )
        raise HTTPException(status_code=502, detail="AI generation failed")

    logger.info(
        "generate type=%s job_id=%d user_id=%d", body.type, job_id, current_user.id
    )
    return GenerateResponse(content=content)
