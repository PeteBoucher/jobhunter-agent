"""User profile routes: view, update, CV upload."""

import logging
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

logger = logging.getLogger("jobhunter.api")
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
    from sqlalchemy.orm import sessionmaker

    from src.database import create_engine_instance
    from src.job_matcher import compute_match_for_user

    engine = create_engine_instance()
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    BATCH = 200
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return
        jobs = session.query(Job).all()
        for i, job in enumerate(jobs, 1):
            compute_match_for_user(session, job, user)
            if i % BATCH == 0:
                session.commit()
        session.commit()
        logger.info("cv_rematch user_id=%d jobs_matched=%d", user_id, len(jobs))
    except Exception as exc:
        logger.error(
            "cv_rematch_error user_id=%d error=%r", user_id, exc, exc_info=True
        )
    finally:
        session.close()


@router.delete("", status_code=204)
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently delete the current user's account and all associated data."""
    from src.models import Application, JobMatch, UserPreferences

    user_id = current_user.id
    db.query(JobMatch).filter(JobMatch.user_id == user_id).delete()
    db.query(Application).filter(Application.user_id == user_id).delete()
    db.query(UserPreferences).filter(UserPreferences.user_id == user_id).delete()
    # Skills have cascade="all, delete-orphan" so they go with the user
    db.delete(current_user)
    db.commit()
    logger.info("account_deleted user_id=%d", user_id)


_MAX_CV_BYTES = 5 * 1024 * 1024  # 5 MB

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _extract_cv_text(content: bytes, filename: str) -> str:
    """Extract plain text from PDF, DOCX, or plain text/markdown CV files."""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == ".pdf":
        import io
        import re

        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError("No text could be extracted from the PDF")
        text = "\n".join(re.sub(r"  +", " ", line) for line in text.split("\n"))
        return text

    if ext == ".docx":
        import io

        from docx import Document

        doc = Document(io.BytesIO(content))
        text = "\n".join(para.text for para in doc.paragraphs).strip()
        if not text:
            raise ValueError("No text could be extracted from the DOCX file")
        return text

    # Plain text / markdown
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("File must be UTF-8 encoded text, PDF, or DOCX")


@router.post("/cv", response_model=UserOut)
async def upload_cv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a CV (PDF, DOCX, TXT or Markdown), extract skills, trigger re-matching."""
    filename = file.filename or ""
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a PDF, DOCX, TXT or Markdown file.",
        )

    content = await file.read(_MAX_CV_BYTES + 1)
    if len(content) > _MAX_CV_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"CV exceeds {_MAX_CV_BYTES // (1024 * 1024)} MB limit",
        )

    try:
        cv_text = _extract_cv_text(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        from cv_parser_llm import parse_cv_with_llm

        from src.cv_parser import CVParser
        from src.user_profile import UserProfile

        parsed = CVParser(cv_text).parse()

        # Fall back to LLM when the regex parser yields too little data
        # (common for multi-column PDFs and non-Markdown CVs).
        _skills = parsed.get("skills", {})
        _total_skills = sum(len(v) for v in _skills.values() if isinstance(v, list))
        _has_name = bool(parsed.get("personal_info", {}).get("name"))
        if not _has_name or _total_skills < 3:
            logger.info(
                "cv_parse_poor_result user=%s skills=%d name=%s; trying LLM",
                current_user.email,
                _total_skills,
                _has_name,
            )
            llm_result = parse_cv_with_llm(cv_text)
            if llm_result:
                parsed = llm_result

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
        profile_manager._sync_skills_from_cv(current_user, parsed.get("skills", {}))
        profile_manager._auto_populate_preferences(prefs, parsed)
        db.commit()

        skill_count = sum(len(v) for v in parsed.get("skills", {}).values())
        logger.info(
            "cv_upload user=%s size_bytes=%d skills_extracted=%d",
            current_user.email,
            len(content),
            skill_count,
        )

    except Exception as exc:
        logger.error(
            "cv_parse_error user=%s error=%r", current_user.email, exc, exc_info=True
        )
        raise HTTPException(status_code=500, detail="CV processing failed")

    # Trigger background re-matching
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/jobs.db")
    background_tasks.add_task(_recompute_matches, current_user.id, db_url)

    db.refresh(current_user)
    return UserOut.model_validate(current_user)
