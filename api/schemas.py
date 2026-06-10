"""API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from research_assistant.source_policy import SourcePolicyConfig


class ResearchRunRequest(BaseModel):
    """Request to run the research pipeline."""

    topic: str = Field(default="CLTV in foreign banks", min_length=3)
    use_live_fetch: bool = False
    fetch_limit: int | None = Field(default=None, ge=1)
    actor_id: str = Field(default="local_analyst", min_length=3)
    actor_role: str = Field(default="analyst", pattern="^(analyst|reviewer|admin)$")
    source_urls: list[HttpUrl] = Field(default_factory=list, max_length=20)
    auto_discover_sources: bool = True
    discovery_max_sources: int = Field(default=8, ge=1, le=20)


class ResearchReviewRequest(BaseModel):
    """Request to review, approve, or reject a generated report."""

    actor_id: str = Field(min_length=3)
    actor_role: str = Field(pattern="^(analyst|reviewer|admin)$")
    decision: str = Field(pattern="^(reviewed|approved|rejected)$")
    notes: str | None = Field(default=None, max_length=1000)


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
    request_settings: dict[str, Any]
    source_policy: dict[str, Any]
    model_gateway: dict[str, Any]
    review: dict[str, Any]
    audit: dict[str, Any]
    artifacts: dict[str, str | None]
    links: dict[str, str | None]


class ResearchRunStatusResponse(ResearchRunResponse):
    """Stored status and metadata for one research run."""


class ResearchRunListResponse(BaseModel):
    """Known API research runs."""

    runs: list[ResearchRunStatusResponse]


class ResearchReviewResponse(BaseModel):
    """Review state after a reviewer action."""

    run_id: str
    review: dict[str, Any]
    audit: dict[str, Any]
    links: dict[str, str | None]


class SourcePolicyUpdateRequest(BaseModel):
    """Request to replace the file-backed source allowlist policy."""

    actor_id: str = Field(min_length=3)
    actor_role: str = Field(pattern="^(analyst|reviewer|admin)$")
    policy: SourcePolicyConfig


class SourcePolicyResponse(BaseModel):
    """Current source allowlist policy and audit metadata."""

    policy: SourcePolicyConfig
    audit: dict[str, Any]
    links: dict[str, str | None]


class AuditEventsResponse(BaseModel):
    """Latest audit events for admin/demo UI inspection."""

    actor_id: str
    count: int
    items: list[dict[str, Any]]
    links: dict[str, str | None]


class ReportResponse(BaseModel):
    """Markdown report payload for one stored research run."""

    run_id: str
    markdown: str


class EvidenceResponse(BaseModel):
    """Structured evidence payload for one stored research run."""

    run_id: str
    items: list[dict[str, Any]]


class ClaimsResponse(BaseModel):
    """Machine-readable claim/evidence traceability for one run."""

    run_id: str
    items: list[dict[str, Any]]


class HealthResponse(BaseModel):
    """Service health payload."""

    status: str
    service: str
