"""Evaluation summary helpers for the Notebook MVP."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .models import CleanDocument, EvidenceItem, ResearchPlan, SourceCandidate, TextChunk


def build_evaluation_summary(
    *,
    plan: ResearchPlan,
    sources: list[SourceCandidate],
    clean_documents: list[CleanDocument],
    chunks: list[TextChunk],
    filtered_chunks: list[TextChunk],
    evidence_items: list[EvidenceItem],
) -> dict[str, Any]:
    """Build compact metrics for manual MVP review."""

    clean_source_ids = {document.source_id for document in clean_documents}
    evidence_source_ids = {item.source_id for item in evidence_items}
    evidence_blocks = Counter(item.research_block or "unknown" for item in evidence_items)
    evidence_by_source = Counter(item.source_id for item in evidence_items)
    source_types = Counter(
        source.source_type.value for source in sources if source.source_id in clean_source_ids
    )
    clean_blocks = Counter(
        source.research_block or "unknown"
        for source in sources
        if source.source_id in clean_source_ids
    )

    required_blocks = list(plan.blocks[:5])

    return {
        "topic": plan.topic,
        "planner_mode": "cltv_demo"
        if "definition_and_business_value" in plan.blocks
        else "generic",
        "seed_source_count": len(sources),
        "clean_document_count": len(clean_documents),
        "clean_source_ids": sorted(clean_source_ids),
        "clean_block_coverage": dict(sorted(clean_blocks.items())),
        "chunk_count": len(chunks),
        "filtered_chunk_count": len(filtered_chunks),
        "noise_reduction": _safe_ratio(len(chunks) - len(filtered_chunks), len(chunks)),
        "evidence_item_count": len(evidence_items),
        "evidence_source_count": len(evidence_source_ids),
        "evidence_block_coverage": dict(sorted(evidence_blocks.items())),
        "source_type_coverage": dict(sorted(source_types.items())),
        "required_blocks": required_blocks,
        "missing_clean_blocks": [
            block for block in required_blocks if clean_blocks.get(block, 0) == 0
        ],
        "missing_evidence_blocks": [
            block for block in required_blocks if evidence_blocks.get(block, 0) == 0
        ],
        "analyzed_sources": _build_analyzed_sources(
            sources=sources,
            clean_source_ids=clean_source_ids,
            evidence_by_source=evidence_by_source,
        ),
        "interpretability_summary": {
            "short_answer_basis": (
                "top_claims_and_evidence" if evidence_items else "insufficient_evidence"
            ),
            "source_diversity": _source_diversity_level(len(evidence_source_ids)),
            "strongest_supported_blocks": [
                block for block, _count in evidence_blocks.most_common(3)
            ],
            "weakest_or_missing_blocks": [
                block for block in required_blocks if evidence_blocks.get(block, 0) == 0
            ],
        },
    }


def write_evaluation_json(summary: dict[str, Any], path: str | Path) -> Path:
    """Write evaluation metrics to JSON for reproducible review."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def _build_analyzed_sources(
    *,
    sources: list[SourceCandidate],
    clean_source_ids: set[str],
    evidence_by_source: Counter[str],
) -> list[dict[str, Any]]:
    return [
        {
            "source_id": source.source_id,
            "title": source.title,
            "url": str(source.url),
            "source_type": source.source_type.value,
            "publisher": source.publisher,
            "research_block": source.research_block,
            "clean_text_available": source.source_id in clean_source_ids,
            "evidence_item_count": evidence_by_source.get(source.source_id, 0),
        }
        for source in sources
    ]


def _source_diversity_level(evidence_source_count: int) -> str:
    if evidence_source_count >= 4:
        return "high"
    if evidence_source_count >= 2:
        return "medium"
    if evidence_source_count == 1:
        return "low"
    return "none"
