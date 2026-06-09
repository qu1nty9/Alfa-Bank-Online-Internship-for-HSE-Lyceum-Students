"""Banking research assistant prototype package."""

from .chunker import chunk_clean_document
from .collector import load_seed_sources
from .config import PipelineConfig, default_pipeline_config
from .evidence import build_evidence_items
from .evaluation import build_evaluation_summary
from .fetcher import fetch_source, fetch_sources_safe
from .filtering import filter_chunks, rank_chunks_bm25
from .llm_gateway import MockLLMGateway
from .models import (
    CleanDocument,
    EvidenceItem,
    FetchResult,
    ParseResult,
    RawDocument,
    ResearchPlan,
    SearchQuery,
    SourceCandidate,
    TextChunk,
)
from .parser import parse_raw_document, parse_raw_documents_safe
from .quality_gate import run_quality_gate
from .report import render_markdown_report
from .sensitivity import SensitivityResult, check_query_sensitivity

__all__ = [
    "CleanDocument",
    "EvidenceItem",
    "FetchResult",
    "MockLLMGateway",
    "ParseResult",
    "PipelineConfig",
    "RawDocument",
    "ResearchPlan",
    "SearchQuery",
    "SensitivityResult",
    "SourceCandidate",
    "TextChunk",
    "build_evidence_items",
    "build_evaluation_summary",
    "chunk_clean_document",
    "check_query_sensitivity",
    "default_pipeline_config",
    "fetch_source",
    "fetch_sources_safe",
    "filter_chunks",
    "load_seed_sources",
    "parse_raw_document",
    "parse_raw_documents_safe",
    "rank_chunks_bm25",
    "render_markdown_report",
    "run_quality_gate",
]
