from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal
import warnings

from pydantic import BaseModel, Field

from .errors import ToolError


class OutputArtifact(BaseModel):
    path: str
    media_type: str
    role: str = "primary"


with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message=r'Field name "schema" in "ToolResult" shadows an attribute in parent "BaseModel"',
        category=UserWarning,
    )

    class ToolResult(BaseModel):
        schema: Literal["ntl.tool.result.v1"] = "ntl.tool.result.v1"
        status: Literal["succeeded", "failed", "cancelled"]
        tool: str
        summary: str
        outputs: list[OutputArtifact] = Field(default_factory=list)
        metrics: dict[str, Any] = Field(default_factory=dict)
        warnings: list[str] = Field(default_factory=list)
        error: ToolError | None = None
        job_id: str | None = None

        @classmethod
        def succeeded(
            cls,
            *,
            tool: str,
            summary: str,
            outputs: list[OutputArtifact] | None = None,
            metrics: dict[str, Any] | None = None,
            warnings: list[str] | None = None,
        ) -> "ToolResult":
            return cls(
                status="succeeded",
                tool=tool,
                summary=summary,
                outputs=[output.model_copy(deep=True) for output in (outputs or [])],
                metrics=deepcopy(metrics) if metrics is not None else {},
                warnings=list(warnings) if warnings is not None else [],
            )

        @classmethod
        def failed(
            cls,
            *,
            tool: str,
            error: ToolError,
            summary: str | None = None,
        ) -> "ToolResult":
            return cls(
                status="failed",
                tool=tool,
                summary=summary or error.message,
                error=error.model_copy(deep=True),
            )
