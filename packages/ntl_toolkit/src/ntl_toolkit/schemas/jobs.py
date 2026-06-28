from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    schema: Literal["ntl.job.v1"] = "ntl.job.v1"
    job_id: str
    tool: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    updated_at: datetime
    request: dict[str, Any] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
