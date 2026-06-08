from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, field_validator


class MatchScoreOut(BaseModel):
    match_score: Optional[float] = None
    skill_score: Optional[float] = None
    title_score: Optional[float] = None
    experience_score: Optional[float] = None
    location_or_remote_score: Optional[float] = None
    salary_score: Optional[float] = None

    # Maximum possible values for each dimension — derived from the scoring
    # constants in src/job_matcher.py. Included so the frontend never needs
    # its own copy of the weights.
    skill_score_max: float = 35.0
    title_score_max: float = 25.0
    experience_score_max: float = 15.0
    location_or_remote_score_max: float = 15.0
    salary_score_max: float = 10.0

    model_config = {"from_attributes": True}


def _coerce_to_list(v: Any) -> Any:
    """Accept a bare string where a list is expected (scraper data quality issue)."""
    if isinstance(v, str):
        return [v] if v.strip() else None
    return v


class JobOut(BaseModel):
    id: int
    source: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    description: Optional[str] = None
    requirements: Optional[List[str]] = None
    nice_to_haves: Optional[List[str]] = None
    apply_url: Optional[str] = None
    posted_date: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    company_industry: Optional[str] = None
    # Caller-populated match scores (joined from JobMatch for current user)
    match: Optional[MatchScoreOut] = None

    @field_validator("requirements", "nice_to_haves", mode="before")
    @classmethod
    def coerce_list_fields(cls, v: Any) -> Any:
        return _coerce_to_list(v)

    model_config = {"from_attributes": True}
