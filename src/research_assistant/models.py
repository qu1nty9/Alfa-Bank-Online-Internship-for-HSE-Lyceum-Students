"""Shared data models for the research assistant prototype."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class SourceType(StrEnum):
    """High-level source categories used for ranking and evidence review."""

    OFFICIAL_BANK = "official_bank"
    REGULATOR = "regulator"
    CONSULTING = "consulting"
    ACADEMIC = "academic"
    VENDOR = "vendor"
    ENCYCLOPEDIA = "encyclopedia"
    RESEARCH_INDEX = "research_index"
    USER_PROVIDED = "user_provided"
    UPLOADED_DOCUMENT = "uploaded_document"
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

    source_id: str = Field(min_length=3)
    url: HttpUrl
    title: str
    source_type: SourceType = SourceType.OTHER
    publisher: str | None = None
    snippet: str | None = None
    query: str | None = None
    research_block: str | None = None
    language: str | None = None
    status: str = "ready"
    notes: str | None = None
    retrieved_at: datetime | None = None


class RawDocument(BaseModel):
    """A fetched source saved before text extraction and cleaning."""

    source_id: str
    url: HttpUrl
    path: Path
    content_type: str | None = None
    status_code: int | None = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    from_cache: bool = False


class FetchResult(BaseModel):
    """Result of one fetch attempt, including recoverable failures."""

    source_id: str
    ok: bool
    raw_document: RawDocument | None = None
    error: str | None = None


class CleanDocument(BaseModel):
    """A cleaned text document ready for chunking and ranking."""

    source_id: str
    title: str | None = None
    url: HttpUrl | None = None
    path: Path
    text: str = Field(min_length=1)
    content_type: str | None = None
    parser_name: str
    char_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ParseResult(BaseModel):
    """Result of one parse attempt, including recoverable failures."""

    source_id: str
    ok: bool
    clean_document: CleanDocument | None = None
    error: str | None = None


class TextChunk(BaseModel):
    """A ranked unit candidate produced from a cleaned document."""

    source_id: str
    chunk_id: str
    text: str = Field(min_length=1)
    title: str | None = None
    url: HttpUrl | None = None
    source_type: SourceType = SourceType.OTHER
    research_block: str | None = None
    start_char: int = 0
    end_char: int = 0
    char_count: int = 0
    token_count: int = 0


class EvidenceItem(BaseModel):
    """A traceable text fragment that can support a report claim."""

    source_id: str
    chunk_id: str
    text: str = Field(min_length=1)
    url: HttpUrl | None = None
    title: str | None = None
    source_type: SourceType = SourceType.OTHER
    research_block: str | None = None
    matched_query: str | None = None
    rank: int | None = None
    relevance_score: float | None = None
    trust_score: float | None = None
    page: int | None = None


class ClaimItem(BaseModel):
    """A machine-readable report claim linked to concrete evidence items."""

    claim_id: str = Field(min_length=3)
    claim_text: str = Field(min_length=1)
    research_block: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    status: str = "draft"
