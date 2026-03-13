"""Job matching engine.

Scores jobs against a user profile across five dimensions:
title similarity, skill coverage, experience level, location/remote fit,
and salary alignment.
"""
import re
from difflib import SequenceMatcher
from typing import List, Optional

from sqlalchemy.orm import Session

from src.models import Job, JobMatch, Skill, User, UserPreferences

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STOPWORDS = {"the", "a", "an", "and", "or", "of", "in", "at", "for", "to", "with"}

_SENIORITY_KEYWORDS: List[tuple] = [
    # (keyword, numeric level) — checked in order; first match wins
    ("chief", 5),
    ("vp ", 5),
    ("vice president", 5),
    ("executive", 5),
    ("director", 4),
    ("head of", 4),
    ("principal", 3),
    ("staff ", 3),
    ("lead", 3),
    ("senior", 3),
    ("expert", 3),
    ("mid-level", 2),
    ("intermediate", 2),
    ("mid ", 2),
    ("junior", 1),
    ("entry", 1),
    ("graduate", 1),
    ("trainee", 1),
    ("intern", 1),
]

_USER_SENIORITY = {"junior": 1, "mid": 2, "senior": 3, "lead": 3}


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _title_words(title: str) -> set:
    return {
        w
        for w in re.sub(r"[^a-z0-9 ]", "", title.lower()).split()
        if w not in _STOPWORDS
    }


def _job_seniority(job: Job) -> Optional[int]:
    """Infer seniority level from job title + first 500 chars of description."""
    text = ((job.title or "") + " " + (job.description or "")[:500]).lower()
    for kw, level in _SENIORITY_KEYWORDS:
        if kw in text:
            return level
    return None


def _location_terms(locs: List[str]) -> List[str]:
    """Extract city/country terms from potentially full street addresses.

    Splits on commas; discards parts containing digits (street numbers/postcodes).
    """
    terms = []
    for loc in locs:
        for part in loc.split(","):
            part = part.strip()
            if part and not re.search(r"\d", part) and len(part) > 2:
                terms.append(part.lower())
    return terms


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


def _score_title(job_title: Optional[str], target_titles: Optional[List[str]]) -> float:
    """Word-level Jaccard similarity, max over all target titles. Up to 30 pts."""
    if not job_title or not target_titles:
        return 0.0
    job_words = _title_words(job_title)
    best = 0.0
    for t in target_titles:
        t_words = _title_words(t)
        if not t_words or not job_words:
            continue
        jaccard = len(job_words & t_words) / len(job_words | t_words)
        # Also include character-level similarity for partial-word matches
        char_sim = _similarity(job_title, t)
        best = max(best, jaccard, char_sim)
    return best * 30.0


def _score_skills(requirements: Optional[List[str]], user_skills: List[Skill]) -> float:
    """Fraction of job requirements covered by user skills. Up to 40 pts."""
    if not requirements or not user_skills:
        return 0.0
    reqs = [r.lower() for r in requirements]
    skill_names = [s.skill_name.lower() for s in user_skills if s.skill_name]
    if not skill_names:
        return 0.0
    req_matches = sum(1 for r in reqs if any(sk in r or r in sk for sk in skill_names))
    coverage = req_matches / len(reqs)
    return min(40.0, coverage * 40.0)


def _score_experience(job: Job, user_prefs: Optional[UserPreferences]) -> float:
    """Compare job seniority to user's level. Up to 10 pts."""
    if not user_prefs or not user_prefs.experience_level:
        return 5.0  # neutral — no preference set
    user_level = _USER_SENIORITY.get(user_prefs.experience_level.lower(), 2)
    job_level = _job_seniority(job)
    if job_level is None:
        return 7.5  # no signal → benefit of the doubt
    diff = abs(user_level - job_level)
    return {0: 10.0, 1: 6.0, 2: 2.0}.get(diff, 0.0)


def _score_location_remote(job: Job, user_prefs: Optional[UserPreferences]) -> float:
    """Remote preference + location substring match. Up to 10 pts."""
    if not user_prefs:
        return 0.0

    # Remote preference check
    if user_prefs.remote_preference:
        pref = user_prefs.remote_preference.lower()
        job_remote = (job.remote or "").lower()
        job_loc = (job.location or "").lower()
        if pref == "remote" and (job_remote == "remote" or "remote" in job_loc):
            return 10.0
        if pref == "hybrid" and job_remote in ("hybrid", "remote"):
            return 7.0
        if pref == "onsite" and job_remote in ("", "onsite"):
            return 10.0

    # Location substring match — extract city/country tokens from full addresses
    if user_prefs.preferred_locations and job.location:
        terms = _location_terms(user_prefs.preferred_locations)
        job_loc = (job.location or "").lower()
        if any(term in job_loc for term in terms):
            return 10.0

    return 0.0


def _score_salary(job: Job, user_prefs: Optional[UserPreferences]) -> float:
    """Gradient salary score. Up to 10 pts.

    Penalises both below-minimum and well-above-maximum (over-level roles).
    """
    if not user_prefs or not user_prefs.salary_min:
        return 10.0  # no preference → full marks
    if not job.salary_min:
        return 7.5  # salary not listed → benefit of the doubt

    sal = job.salary_min
    s_min = user_prefs.salary_min
    s_max = user_prefs.salary_max  # may be None

    # --- Below-minimum penalty ---
    if sal < s_min * 0.75:
        return 0.0
    if sal < s_min * 0.90:
        below_score = 3.0
    elif sal < s_min:
        below_score = 6.0
    else:
        below_score = 10.0

    # --- Above-maximum penalty (over-level / directorial roles) ---
    if s_max and sal > s_max:
        ratio = sal / s_max
        if ratio > 1.5:
            return min(below_score, 2.0)  # > 50% over max — poor fit
        if ratio > 1.25:
            return min(below_score, 5.0)  # 25–50% over max
        return min(below_score, 8.0)  # up to 25% over max — close enough

    return below_score


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def compute_match_for_user(session: Session, job: Job, user: User) -> JobMatch:
    """Compute match score for a single user and job and persist a JobMatch."""
    prefs = user.preferences
    skills = user.skills or []

    title_score = _score_title(job.title, prefs.target_titles if prefs else None)
    skill_score = _score_skills(job.requirements, skills)
    experience_score = _score_experience(job, prefs)
    location_score = _score_location_remote(job, prefs)
    salary_score = _score_salary(job, prefs)

    total = max(
        0.0,
        min(
            100.0,
            title_score
            + skill_score
            + experience_score
            + location_score
            + salary_score,
        ),
    )

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
