"""Build and export evidence tables from ranked chunks."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import EvidenceItem, SearchQuery, TextChunk


def build_evidence_items(
    ranked_chunks: list[tuple[TextChunk, SearchQuery, float]],
    *,
    max_items: int = 20,
) -> list[EvidenceItem]:
    """Convert ranked chunk-query matches into deduplicated evidence items."""

    sorted_matches = sorted(ranked_chunks, key=lambda item: item[2], reverse=True)
    selected_matches: list[tuple[TextChunk, SearchQuery, float]] = []
    covered_blocks: set[str] = set()
    selected_chunk_ids: set[str] = set()

    for chunk, query, score in sorted_matches:
        if chunk.chunk_id in selected_chunk_ids:
            continue
        if query.research_block in covered_blocks:
            continue
        selected_matches.append((chunk, query, score))
        selected_chunk_ids.add(chunk.chunk_id)
        covered_blocks.add(query.research_block)
        if len(selected_matches) >= max_items:
            break

    for chunk, query, score in sorted_matches:
        if len(selected_matches) >= max_items:
            break
        if chunk.chunk_id in selected_chunk_ids:
            continue
        selected_matches.append((chunk, query, score))
        selected_chunk_ids.add(chunk.chunk_id)

    selected_matches.sort(key=lambda item: item[2], reverse=True)

    evidence_items: list[EvidenceItem] = []
    seen_chunk_ids: set[str] = set()

    for chunk, query, score in selected_matches:
        if chunk.chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk.chunk_id)
        evidence_items.append(
            EvidenceItem(
                source_id=chunk.source_id,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                url=chunk.url,
                title=chunk.title,
                source_type=chunk.source_type,
                research_block=query.research_block,
                matched_query=query.query,
                rank=len(evidence_items) + 1,
                relevance_score=round(score, 4),
            )
        )
        if len(evidence_items) >= max_items:
            break

    return evidence_items


def write_evidence_csv(evidence_items: list[EvidenceItem], path: str | Path) -> Path:
    """Write evidence items as a compact CSV for manual review."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "rank",
                "source_id",
                "chunk_id",
                "source_type",
                "research_block",
                "matched_query",
                "relevance_score",
                "title",
                "url",
                "text_preview",
            ],
        )
        writer.writeheader()
        for item in evidence_items:
            writer.writerow(
                {
                    "rank": item.rank,
                    "source_id": item.source_id,
                    "chunk_id": item.chunk_id,
                    "source_type": item.source_type.value,
                    "research_block": item.research_block,
                    "matched_query": item.matched_query,
                    "relevance_score": item.relevance_score,
                    "title": item.title,
                    "url": str(item.url) if item.url else "",
                    "text_preview": _preview(item.text),
                }
            )

    return output_path


def write_evidence_jsonl(evidence_items: list[EvidenceItem], path: str | Path) -> Path:
    """Write evidence items as JSONL for downstream synthesis."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for item in evidence_items:
            file.write(item.model_dump_json() + "\n")

    return output_path


def _preview(text: str, *, max_chars: int = 350) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[: max_chars - 3].rstrip() + "..."
