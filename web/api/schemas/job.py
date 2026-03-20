from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


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

    model_config = {"from_attributes": True}
