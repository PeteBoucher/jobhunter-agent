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
    # Capped penalty subtracted from the sum of the five dimensions above for
    # similarity to jobs this user has rejected (company repetition / title
    # similarity) — see job_matcher._rejection_penalty(). Not one of the five
    # weighted dimensions, so it has no corresponding *_max field.
    rejection_penalty: float = 0.0

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


class OtherLocationOut(BaseModel):
    """A sibling posting collapsed into a feed card (see GET /jobs grouping)."""

    id: int
    location: Optional[str] = None
    country: Optional[str] = None


class JobSummaryOut(BaseModel):
    """A job as listed on a feed card — everything except ``description``.

    List endpoints (GET /jobs, GET /jobs/rejected) return this: the cards never
    show the description, and it is by far the largest column, so shipping it
    for every card wasted memory on the 512MB Render instance. GET /jobs/{id}
    returns the full ``JobOut``.
    """

    id: int
    source: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    remote: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    requirements: Optional[List[str]] = None
    nice_to_haves: Optional[List[str]] = None
    apply_url: Optional[str] = None
    posted_date: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    company_industry: Optional[str] = None
    # Caller-populated match scores (joined from JobMatch for current user)
    match: Optional[MatchScoreOut] = None
    # Set True only by GET /jobs/rejected; unset (None) on the normal feed,
    # which excludes rejected jobs entirely rather than flagging them.
    is_rejected: Optional[bool] = None
    rejection_reason: Optional[str] = None
    # Set only by GET /jobs: other postings of the same role (same company,
    # normalised title and remote type) collapsed into this card, e.g. one
    # role posted once per country. Empty elsewhere.
    other_locations: List[OtherLocationOut] = []

    @field_validator("requirements", "nice_to_haves", mode="before")
    @classmethod
    def coerce_list_fields(cls, v: Any) -> Any:
        return _coerce_to_list(v)

    model_config = {"from_attributes": True}


class JobOut(JobSummaryOut):
    """A single job with its full description (GET /jobs/{id})."""

    description: Optional[str] = None
