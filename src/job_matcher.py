"""Simple job matching engine.

Provides a lightweight scoring function to rank jobs against a user
profile using heuristics: title similarity, skill overlap, experience,
location/remote fit, and salary alignment.
"""
from difflib import SequenceMatcher
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models import Job, JobMatch, Skill, User, UserPreferences


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _score_title(job_title: Optional[str], target_titles: Optional[List[str]]) -> float:
    if not job_title or not target_titles:
        return 0.0
    best = 0.0
    for t in target_titles:
        best = max(best, _similarity(job_title, t))
    return best * 30.0  # up to 30 points


def _score_skills(requirements: Optional[List[str]], user_skills: List[Skill]) -> float:
    if not requirements or not user_skills:
        return 0.0
    reqs = [r.lower() for r in requirements]
    skill_names = [s.skill_name.lower() for s in user_skills if s.skill_name]
    matches = sum(1 for sk in skill_names if any(sk in r or r in sk for r in reqs))
    if not skill_names:
        return 0.0
    ratio = matches / len(skill_names)
    return min(40.0, ratio * 40.0)  # up to 40 points


def _score_experience(job: Job, user_prefs: Optional[UserPreferences]) -> float:
    # Placeholder: award small score if experience level present
    if not user_prefs or not user_prefs.experience_level:
        return 0.0
    # crude mapping
    mapping = {"junior": 0.5, "mid": 0.75, "senior": 1.0, "lead": 1.0}
    desired = user_prefs.experience_level.lower()
    score = mapping.get(desired, 0.75)
    return score * 10.0  # up to 10 points


def _score_location_remote(job: Job, user_prefs: Optional[UserPreferences]) -> float:
    if not user_prefs:
        return 0.0
    # remote preference
    if user_prefs.remote_preference:
        pref = user_prefs.remote_preference.lower()
        if pref == "remote" and (
            job.remote == "remote"
            or (job.location and "remote" in job.location.lower())
        ):
            return 10.0
        if pref == "hybrid" and job.remote in ("hybrid", "remote"):
            return 7.0
        if pref == "onsite" and job.remote in (None, "onsite"):
            return 10.0
    # location matching (simple substring)
    if user_prefs.preferred_locations and job.location:
        locs = [loc.lower() for loc in user_prefs.preferred_locations]
        if any(loc in (job.location or "").lower() for loc in locs):
            return 10.0
    return 0.0


def _score_salary(job: Job, user_prefs: Optional[UserPreferences]) -> float:
    # No user salary preference → not filtering by salary, full marks
    if not user_prefs or not user_prefs.salary_min:
        return 10.0
    # Job has no salary listed → can't confirm a mismatch, benefit of the doubt
    if not job.salary_min:
        return 10.0
    # Job explicitly meets the minimum → full marks
    if job.salary_min >= user_prefs.salary_min:
        return 10.0
    # Job salary is explicitly below minimum → penalise
    return 0.0


def compute_match_for_user(session: Session, job: Job, user: User) -> JobMatch:
    """Compute match score for a single user and job and persist a JobMatch.

    Returns the created JobMatch instance.
    """
    # Load preferences and skills
    prefs = user.preferences
    skills = user.skills or []

    title_score = _score_title(job.title, prefs.target_titles if prefs else None)
    skill_score = _score_skills(job.requirements, skills)
    experience_score = _score_experience(job, prefs)
    location_score = _score_location_remote(job, prefs)
    salary_score = _score_salary(job, prefs)

    total = title_score + skill_score + experience_score + location_score + salary_score
    # clamp to 0-100
    total = max(0.0, min(100.0, total))

    jm = (
        session.query(JobMatch)
        .filter(JobMatch.job_id == job.id, JobMatch.user_id == user.id)
        .first()
    )
    if jm is None:
        jm = JobMatch(job_id=job.id, user_id=user.id)
        session.add(jm)

    jm.match_score = total
    jm.skill_score = skill_score
    jm.title_score = title_score
    jm.experience_score = experience_score
    jm.location_or_remote_score = location_score
    jm.salary_score = salary_score
    session.commit()
    return jm


__all__ = ["compute_match_for_user"]
