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

    model_config = {"from_attributes": True}
