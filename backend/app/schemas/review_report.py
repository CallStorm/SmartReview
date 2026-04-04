"""Unified review report JSON (v1) for UI and Word comments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportIssue(BaseModel):
    issue_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    severity: Literal["error", "warning", "info"] = "error"
    message: str
    evidence: str = ""
    anchor: dict[str, Any] = Field(default_factory=dict)
    related: dict[str, Any] = Field(default_factory=dict)


class ReportStep(BaseModel):
    step_id: str
    passed: bool
    summary: str = ""
    issues: list[ReportIssue] = Field(default_factory=list)


class ReviewReportV1(BaseModel):
    version: Literal[1] = 1
    steps: list[ReportStep] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    model_provider: str | None = None

    def to_json_str(self) -> str:
        import json

        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False)
