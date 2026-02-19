"""Schema definitions for scene manifests, task samples, and predictions."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .constants import TASK_SPECS, TRACKS

try:
    from shapely import wkt
except Exception:  # pragma: no cover - fallback when shapely is unavailable
    wkt = None


_OPTION_LABEL_PATTERN = re.compile(r"^[A-Z]$")


class SceneRecord(BaseModel):
    """Canonical scene record used by the benchmark."""

    model_config = ConfigDict(extra="allow")

    scene_id: str
    event_id: str
    hazard_type: str
    aoi_wkt: str
    pre_start: date
    pre_end: date
    post_start: date
    post_end: date
    quality_score: float = Field(ge=0.0, le=1.0)
    split: Literal["train", "val", "public_test", "private_test"]
    license_tag: str
    source: str = ""
    mean_pre: float | None = None
    mean_post: float | None = None
    recovery_index: float | None = Field(default=None, ge=0.0, le=1.0)
    cloud_free_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    blackout_cluster_count: int | None = Field(default=None, ge=0)
    affected_sector: Literal["A", "B", "C", "D"] | None = None

    @field_validator("scene_id", "event_id", "hazard_type", "license_tag")
    @classmethod
    def _non_empty_str(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("aoi_wkt")
    @classmethod
    def _validate_aoi_wkt(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("aoi_wkt cannot be empty")
        if wkt is not None:
            try:
                geom = wkt.loads(text)
            except Exception as exc:
                raise ValueError(f"invalid WKT geometry: {exc}") from exc
            if geom.is_empty:
                raise ValueError("geometry is empty")
            if not geom.is_valid:
                raise ValueError("geometry is not valid")
        return text

    @model_validator(mode="after")
    def _validate_temporal_windows(self) -> "SceneRecord":
        if self.pre_start > self.pre_end:
            raise ValueError("pre_start must be <= pre_end")
        if self.post_start > self.post_end:
            raise ValueError("post_start must be <= post_end")
        if self.pre_end > self.post_start:
            raise ValueError("pre_end must be <= post_start")
        return self


class TaskSample(BaseModel):
    """Canonical benchmark sample used in task files."""

    model_config = ConfigDict(extra="allow")

    sample_id: str
    scene_id: str
    task_id: str
    question: str
    options: List[str] = Field(default_factory=list)
    answer: str | int | float | Dict[str, Any]
    source: str
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("sample_id", "scene_id", "task_id", "question", "source")
    @classmethod
    def _non_empty_fields(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("field cannot be empty")
        return text

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, value: str) -> str:
        if value not in TASK_SPECS:
            raise ValueError(f"unknown task_id '{value}'")
        return value

    @model_validator(mode="after")
    def _validate_task_payload(self) -> "TaskSample":
        spec = TASK_SPECS[self.task_id]
        if spec["task_type"] == "objective":
            if not self.options:
                raise ValueError("objective tasks require non-empty options")
            if isinstance(self.answer, str):
                label = self.answer.strip().upper()
                if not _OPTION_LABEL_PATTERN.match(label):
                    raise ValueError("objective task answer must be a single uppercase option label")
            else:
                raise ValueError("objective task answer must be a string label")
        else:
            if not isinstance(self.answer, str):
                raise ValueError("text task answer must be a string")
            if not self.answer.strip():
                raise ValueError("text task answer cannot be empty")
        return self


class PredictionRecord(BaseModel):
    """Submission row schema."""

    model_config = ConfigDict(extra="allow")

    sample_id: str
    prediction: str | int | float | Dict[str, Any]
    model_id: str
    track: Literal[TRACKS[0], TRACKS[1]]

    @field_validator("sample_id", "model_id")
    @classmethod
    def _validate_required_strings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must be non-empty")
        return value

