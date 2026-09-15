from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RejectionCreate(BaseModel):
    reason: Optional[str] = None


class RejectionOut(BaseModel):
    job_id: int
    reason: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
