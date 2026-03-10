from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ApplicationCreate(BaseModel):
    job_id: int
    notes: Optional[str] = None
    status: str = "applied"


class ApplicationUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    user_id: Optional[int] = None
    status: Optional[str] = None
    application_date: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    job_title: Optional[str] = None
    job_company: Optional[str] = None

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, **kwargs):
        instance = super().model_validate(obj, **kwargs)
        if hasattr(obj, "job") and obj.job:
            instance.job_title = obj.job.title
            instance.job_company = obj.job.company
        return instance
