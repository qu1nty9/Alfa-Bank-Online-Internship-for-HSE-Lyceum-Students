"""API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ResearchRunRequest(BaseModel):
    """Request to run the research pipeline."""

    topic: str = Field(default="CLTV in foreign banks", min_length=3)
    use_live_fetch: bool = False
    fetch_limit: int | None = Field(default=None, ge=1)


class ResearchRunResponse(BaseModel):
    """Response returned after a research pipeline run is stored."""

    run_id: str
    status: str
    topic: str
    created_at: datetime
    completed_at: datetime | None = None
    sensitivity: str
    quality_gate: str
    evaluation_summary: dict[str, Any]
    artifacts: dict[str, str | None]
    links: dict[str, str | None]


class ResearchRunStatusResponse(ResearchRunResponse):
    """Stored status and metadata for one research run."""


class ResearchRunListResponse(BaseModel):
    """Known API research runs."""

    runs: list[ResearchRunStatusResponse]


class ReportResponse(BaseModel):
    """Markdown report payload for one stored research run."""

    run_id: str
    markdown: str


class EvidenceResponse(BaseModel):
    """Structured evidence payload for one stored research run."""

    run_id: str
    items: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Service health payload."""

    status: str
    service: str
