"""Build machine-readable claim/evidence traceability tables."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import ClaimItem, EvidenceItem

BLOCK_CLAIM_PREFIXES = {
    "definition_and_context": "{topic} has relevant definition and context evidence",
    "definition_and_business_value": "{topic} has relevant business-value evidence",
    "use_cases_and_examples": "{topic} has evidence about use cases and examples",
    "methods_and_approaches": "{topic} has evidence about methods and implementation approaches",
    "calculation_methods": "{topic} has evidence about calculation or analytical methods",
    "data_and_requirements": "{topic} has evidence about data, metrics, or requirements",
    "required_data": "{topic} has evidence about required data and inputs",
    "banking_use_cases": "{topic} has evidence about banking use cases",
    "risks_and_limitations": "{topic} needs explicit risk and limitation review",
    "implementation_considerations": "{topic} has evidence about implementation considerations",
}


def build_claim_items(
    evidence_items: list[EvidenceItem],
    *,
    topic: str | None = None,
    max_claims: int = 12,
) -> list[ClaimItem]:
    """Create traceable draft claims from selected evidence items."""

    claims: list[ClaimItem] = []
    for item in evidence_items[:max_claims]:
        evidence_id = evidence_item_id(item)
        block = item.research_block or "unknown"
        prefix = _claim_prefix(block, topic)
        claims.append(
            ClaimItem(
                claim_id=f"claim_{len(claims) + 1:03d}",
                claim_text=f"{prefix}: {_preview(item.text)}",
                research_block=item.research_block,
                evidence_ids=[evidence_id],
                source_ids=[item.source_id],
                confidence=_confidence_from_score(item.relevance_score),
                status="draft",
            )
        )

    return claims


def evidence_item_id(item: EvidenceItem) -> str:
    """Return a stable evidence identifier used in claim links."""

    return f"{item.source_id}/{item.chunk_id}"


def _claim_prefix(block: str, topic: str | None) -> str:
    topic_text = topic or "The research topic"
    template = BLOCK_CLAIM_PREFIXES.get(
        block,
        "{topic} has evidence relevant to " + block,
    )
    return template.format(topic=topic_text)


def write_claims_csv(claim_items: list[ClaimItem], path: str | Path) -> Path:
    """Write claim/evidence links as CSV for manual review."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "claim_id",
                "research_block",
                "confidence",
                "status",
                "evidence_ids",
                "source_ids",
                "claim_text",
            ],
        )
        writer.writeheader()
        for item in claim_items:
            writer.writerow(
                {
                    "claim_id": item.claim_id,
                    "research_block": item.research_block or "",
                    "confidence": item.confidence,
                    "status": item.status,
                    "evidence_ids": ";".join(item.evidence_ids),
                    "source_ids": ";".join(item.source_ids),
                    "claim_text": item.claim_text,
                }
            )

    return output_path


def write_claims_jsonl(claim_items: list[ClaimItem], path: str | Path) -> Path:
    """Write claim/evidence links as JSONL for API/frontend integrations."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as file:
        for item in claim_items:
            file.write(item.model_dump_json() + "\n")

    return output_path


def _confidence_from_score(score: float | None) -> str:
    if score is None:
        return "medium"
    if score >= 3:
        return "high"
    if score >= 1:
        return "medium"
    return "low"


def _preview(text: str, *, max_chars: int = 220) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[: max_chars - 3].rstrip() + "..."
