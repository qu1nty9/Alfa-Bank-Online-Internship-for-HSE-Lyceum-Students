"""Banking research assistant prototype package."""

from .chunker import chunk_clean_document
from .collector import load_seed_sources
from .config import PipelineConfig, default_pipeline_config
from .evidence import build_evidence_items
from .evaluation import build_evaluation_summary
from .fetcher import fetch_source, fetch_sources_safe
from .filtering import filter_chunks, rank_chunks_bm25
from .llm_gateway import (
    LLMGatewayConfig,
    LLMGatewayMetadata,
    GigaChatLLMGateway,
    MockLLMGateway,
    OfflineTemplateLLMGateway,
    OpenAICompatibleLLMGateway,
    build_llm_gateway,
    default_llm_gateway_metadata,
    llm_gateway_config_from_env,
)
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
from .source_policy import (
    SourcePolicyConfig,
    default_source_policy_config,
    load_source_policy_config,
    save_source_policy_config,
    summarize_source_policy,
)

__all__ = [
    "CleanDocument",
    "EvidenceItem",
    "FetchResult",
    "GigaChatLLMGateway",
    "LLMGatewayConfig",
    "LLMGatewayMetadata",
    "MockLLMGateway",
    "OfflineTemplateLLMGateway",
    "OpenAICompatibleLLMGateway",
    "ParseResult",
    "PipelineConfig",
    "RawDocument",
    "ResearchPlan",
    "SearchQuery",
    "SensitivityResult",
    "SourceCandidate",
    "SourcePolicyConfig",
    "TextChunk",
    "build_evidence_items",
    "build_llm_gateway",
    "build_evaluation_summary",
    "chunk_clean_document",
    "check_query_sensitivity",
    "default_pipeline_config",
    "default_source_policy_config",
    "default_llm_gateway_metadata",
    "fetch_source",
    "fetch_sources_safe",
    "filter_chunks",
    "load_seed_sources",
    "load_source_policy_config",
    "llm_gateway_config_from_env",
    "parse_raw_document",
    "parse_raw_documents_safe",
    "rank_chunks_bm25",
    "render_markdown_report",
    "run_quality_gate",
    "save_source_policy_config",
    "summarize_source_policy",
]
