"""Build lightweight claim/evidence/source graph artifacts."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def build_knowledge_graph(
    *,
    evidence_items: list[dict[str, Any]],
    claim_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a small directed graph for UI and downstream integrations.

    The graph is intentionally plain JSON: no graph database is required for
    the MVP, and banks can map this shape into their own lineage tooling later.
    """

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    evidence_by_id: dict[str, dict[str, Any]] = {}
    source_blocks: dict[str, set[str]] = defaultdict(set)
    source_evidence_count: Counter[str] = Counter()

    for evidence in evidence_items:
        evidence_id = f"{evidence.get('source_id')}/{evidence.get('chunk_id')}"
        source_id = str(evidence.get("source_id") or "unknown_source")
        block = str(evidence.get("research_block") or "unknown")
        source_type = str(evidence.get("source_type") or "other")

        evidence_by_id[evidence_id] = evidence
        source_blocks[source_id].add(block)
        source_evidence_count[source_id] += 1

        nodes[f"source:{source_id}"] = {
            "id": f"source:{source_id}",
            "kind": "source",
            "label": source_id,
            "source_type": source_type,
            "title": evidence.get("title"),
            "url": evidence.get("url"),
        }
        nodes[f"evidence:{evidence_id}"] = {
            "id": f"evidence:{evidence_id}",
            "kind": "evidence",
            "label": evidence.get("chunk_id") or evidence_id,
            "source_id": source_id,
            "research_block": block,
            "relevance_score": evidence.get("relevance_score"),
            "text_preview": _preview(str(evidence.get("text") or "")),
        }
        edges.append(
            {
                "from": f"evidence:{evidence_id}",
                "to": f"source:{source_id}",
                "relation": "from_source",
            }
        )

    for claim in claim_items:
        claim_id = str(claim.get("claim_id") or "claim_unknown")
        nodes[f"claim:{claim_id}"] = {
            "id": f"claim:{claim_id}",
            "kind": "claim",
            "label": claim_id,
            "confidence": claim.get("confidence"),
            "research_block": claim.get("research_block"),
            "text_preview": _preview(str(claim.get("claim_text") or "")),
        }
        for evidence_id in claim.get("evidence_ids") or []:
            if evidence_id not in evidence_by_id:
                continue
            edges.append(
                {
                    "from": f"claim:{claim_id}",
                    "to": f"evidence:{evidence_id}",
                    "relation": "supported_by",
                }
            )

    source_summaries = [
        {
            "source_id": source_id,
            "evidence_count": source_evidence_count[source_id],
            "research_blocks": sorted(blocks),
        }
        for source_id, blocks in sorted(source_blocks.items())
    ]

    return {
        "summary": {
            "source_count": len(source_summaries),
            "evidence_count": len(evidence_items),
            "claim_count": len(claim_items),
            "edge_count": len(edges),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
        "source_summaries": source_summaries,
    }


def _preview(text: str, *, max_chars: int = 180) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[: max_chars - 3].rstrip() + "..."
