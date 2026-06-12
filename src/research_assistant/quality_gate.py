"""Quality gate checks for the Notebook MVP report."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .models import EvidenceItem


class QualityCheck(BaseModel):
    """One quality gate check result."""

    name: str
    passed: bool
    severity: str
    detail: str


class QualityGateResult(BaseModel):
    """Aggregated quality gate result."""

    status: str
    checks: list[QualityCheck]


def run_quality_gate(
    *,
    evidence_items: list[EvidenceItem],
    evaluation_summary: dict[str, Any],
    report_markdown: str,
    min_clean_documents: int = 5,
    min_evidence_items: int = 8,
    min_evidence_sources: int = 4,
) -> QualityGateResult:
    """Run transparent MVP quality checks before accepting the notebook output."""

    checks = [
        QualityCheck(
            name="has_clean_documents",
            passed=evaluation_summary.get("clean_document_count", 0) > 0,
            severity="fail",
            detail="At least one clean document is required to build a report.",
        ),
        QualityCheck(
            name="clean_document_count_target",
            passed=evaluation_summary.get("clean_document_count", 0) >= min_clean_documents,
            severity="warn",
            detail=(
                f"Clean documents: {evaluation_summary.get('clean_document_count', 0)} "
                f"(target >= {min_clean_documents})."
            ),
        ),
        QualityCheck(
            name="has_evidence_items",
            passed=len(evidence_items) > 0,
            severity="fail",
            detail="At least one evidence item is required to support any conclusion.",
        ),
        QualityCheck(
            name="evidence_item_count_target",
            passed=len(evidence_items) >= min_evidence_items,
            severity="warn",
            detail=f"Evidence items: {len(evidence_items)} (target >= {min_evidence_items}).",
        ),
        QualityCheck(
            name="evidence_source_diversity",
            passed=evaluation_summary.get("evidence_source_count", 0) >= min_evidence_sources,
            severity="warn",
            detail=(
                f"Evidence sources: {evaluation_summary.get('evidence_source_count', 0)} "
                f"(target >= {min_evidence_sources})."
            ),
        ),
        QualityCheck(
            name="required_evidence_blocks",
            passed=not evaluation_summary.get("missing_evidence_blocks"),
            severity="warn",
            detail=f"Missing evidence blocks: {evaluation_summary.get('missing_evidence_blocks', [])}.",
        ),
        QualityCheck(
            name="report_has_unknowns",
            passed="## Unknowns" in report_markdown,
            severity="fail",
            detail="Generated report must include an Unknowns section.",
        ),
        QualityCheck(
            name="report_has_evidence_table",
            passed="## Evidence table" in report_markdown and "| rank | source_id |" in report_markdown,
            severity="fail",
            detail="Generated report must include an evidence table.",
        ),
        QualityCheck(
            name="all_evidence_items_have_source_ids",
            passed=all(item.source_id and item.chunk_id for item in evidence_items),
            severity="fail",
            detail="Every evidence item must have source_id and chunk_id.",
        ),
        QualityCheck(
            name="claim_critic_has_no_unsupported_claims",
            passed=evaluation_summary.get("critic_summary", {}).get(
                "unsupported_claim_count",
                0,
            )
            == 0,
            severity="fail",
            detail=(
                "Unsupported claims: "
                f"{evaluation_summary.get('critic_summary', {}).get('unsupported_claim_count', 0)}."
            ),
        ),
        QualityCheck(
            name="claim_critic_has_no_numeric_warnings",
            passed=evaluation_summary.get("critic_summary", {}).get(
                "numeric_warning_count",
                0,
            )
            == 0,
            severity="warn",
            detail=(
                "Numeric claim warnings: "
                f"{evaluation_summary.get('critic_summary', {}).get('numeric_warning_count', 0)}."
            ),
        ),
        QualityCheck(
            name="claim_critic_has_no_review_claims",
            passed=evaluation_summary.get("critic_summary", {}).get(
                "needs_review_claim_count",
                0,
            )
            == 0,
            severity="warn",
            detail=(
                "Claims needing review: "
                f"{evaluation_summary.get('critic_summary', {}).get('needs_review_claim_count', 0)}."
            ),
        ),
    ]

    has_failed_required_check = any(
        not check.passed and check.severity == "fail" for check in checks
    )
    has_warning = any(not check.passed and check.severity == "warn" for check in checks)
    if has_failed_required_check:
        status = "fail"
    elif has_warning:
        status = "warn"
    else:
        status = "pass"

    return QualityGateResult(status=status, checks=checks)
