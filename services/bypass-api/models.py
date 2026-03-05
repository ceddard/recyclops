from pydantic import BaseModel
from typing import Optional


class BypassCreate(BaseModel):
    repo: str
    pr_number: int
    reason: str
    created_by: str
    expires_in_hours: int = 24


class BypassResponse(BaseModel):
    repo: str
    pr_number: int
    reason: str
    created_by: str
    expires_at: int
    created_at: int
