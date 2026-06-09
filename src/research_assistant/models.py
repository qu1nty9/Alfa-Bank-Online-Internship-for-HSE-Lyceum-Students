"""Shared data models for the research assistant prototype."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl


class SourceType(StrEnum):
    """High-level source categories used for ranking and evidence review."""

    OFFICIAL_BANK = "official_bank"
    REGULATOR = "regulator"
    CONSULTING = "consulting"
    ACADEMIC = "academic"
    VENDOR = "vendor"
    NEWS = "news"
    OTHER = "other"


class SearchQuery(BaseModel):
    """A concrete public search query produced by the research planner."""

    query: str = Field(min_length=3)
    research_block: str = Field(min_length=3)
    geography: str | None = None
    language: str | None = None


class ResearchPlan(BaseModel):
    """Structured plan for one research run."""

    topic: str = Field(min_length=3)
    blocks: list[str] = Field(default_factory=list)
    queries: list[SearchQuery] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SourceCandidate(BaseModel):
    """A source before final filtering and evidence extraction."""

    url: HttpUrl
    title: str
    source_type: SourceType = SourceType.OTHER
    publisher: str | None = None
    snippet: str | None = None
    query: str | None = None
    retrieved_at: datetime | None = None


class EvidenceItem(BaseModel):
    """A traceable text fragment that can support a report claim."""

    source_id: str
    chunk_id: str
    text: str = Field(min_length=1)
    url: HttpUrl | None = None
    title: str | None = None
    source_type: SourceType = SourceType.OTHER
    relevance_score: float | None = None
    trust_score: float | None = None
    page: int | None = None

