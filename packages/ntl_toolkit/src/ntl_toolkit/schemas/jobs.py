from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import warnings

from pydantic import BaseModel, Field


with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "schema" in "JobRecord" shadows an attribute in parent "BaseModel"',
        category=UserWarning,
    )

    class JobRecord(BaseModel):
        schema: Literal["ntl.job.v1"] = "ntl.job.v1"
        job_id: str
        tool: str
        status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
        created_at: datetime
        updated_at: datetime
        request: dict[str, Any] = Field(default_factory=dict)
        outputs: list[str] = Field(default_factory=list)
