from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SkillOut(BaseModel):
    id: int
    skill_name: str
    proficiency: Optional[int] = None
    category: Optional[str] = None

    model_config = {"from_attributes": True}


class PreferencesOut(BaseModel):
    target_titles: Optional[List[str]] = None
    target_industries: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    experience_level: Optional[str] = None
    remote_preference: Optional[str] = None
    contract_types: Optional[List[str]] = None

    model_config = {"from_attributes": True}


class PreferencesUpdate(BaseModel):
    target_titles: Optional[List[str]] = None
    target_industries: Optional[List[str]] = None
    preferred_locations: Optional[List[str]] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    experience_level: Optional[str] = None
    remote_preference: Optional[str] = None
    contract_types: Optional[List[str]] = None


class UserOut(BaseModel):
    id: int
    google_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    location: Optional[str] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    skills: List[SkillOut] = []
    preferences: Optional[PreferencesOut] = None

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    title: Optional[str] = None
