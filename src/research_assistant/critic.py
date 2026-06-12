"""Deterministic claim/evidence critic for traceable draft reports."""

from __future__ import annotations

import re
from statistics import mean
from typing import Any

from pydantic import BaseModel

from .chunker import simple_tokenize
from .claims import evidence_item_id
from .models import ClaimItem, EvidenceItem

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "with",
    "как",
    "для",
    "или",
    "это",
    "что",
}


class CriticFinding(BaseModel):
    """One deterministic claim-support finding."""

    claim_id: str
    status: str
    severity: str
    reasons: list[str]
    evidence_ids: list[str]
    overlap_score: float
    numeric_values: list[str] = []


class CriticSummary(BaseModel):
    """Aggregated claim critic output for reports and quality gates."""

    status: str
    finding_count: int
    supported_claim_count: int
    needs_review_claim_count: int
    unsupported_claim_count: int
    numeric_warning_count: int
    average_overlap_score: float
    findings: list[CriticFinding]


def apply_claim_critic(
    claim_items: list[ClaimItem],
    evidence_items: list[EvidenceItem],
    *,
    min_overlap_score: float = 0.08,
) -> tuple[list[ClaimItem], dict[str, Any]]:
    """Update claim statuses and return a machine-readable critic summary."""

    summary = critique_claims(
        claim_items,
        evidence_items,
        min_overlap_score=min_overlap_score,
    )
    finding_by_claim_id = {finding.claim_id: finding for finding in summary.findings}
    updated_claims = [
        claim.model_copy(update={"status": finding_by_claim_id[claim.claim_id].status})
        for claim in claim_items
    ]
    return updated_claims, summary.model_dump(mode="json")


def critique_claims(
    claim_items: list[ClaimItem],
    evidence_items: list[EvidenceItem],
    *,
    min_overlap_score: float = 0.08,
) -> CriticSummary:
    """Check whether each claim is explicitly backed by referenced evidence."""

    evidence_by_id = {evidence_item_id(item): item for item in evidence_items}
    findings = [
        _critique_claim(
            claim,
            evidence_by_id,
            min_overlap_score=min_overlap_score,
        )
        for claim in claim_items
    ]
    unsupported_count = sum(1 for finding in findings if finding.status == "unsupported")
    needs_review_count = sum(1 for finding in findings if finding.status == "needs_review")
    numeric_warning_count = sum(
        1 for finding in findings if "numeric_value_not_in_evidence" in finding.reasons
    )
    if unsupported_count:
        status = "fail"
    elif needs_review_count or numeric_warning_count:
        status = "warn"
    else:
        status = "pass"

    return CriticSummary(
        status=status,
        finding_count=len(findings),
        supported_claim_count=sum(1 for finding in findings if finding.status == "supported"),
        needs_review_claim_count=needs_review_count,
        unsupported_claim_count=unsupported_count,
        numeric_warning_count=numeric_warning_count,
        average_overlap_score=round(mean([item.overlap_score for item in findings]), 4)
        if findings
        else 0.0,
        findings=findings,
    )


def _critique_claim(
    claim: ClaimItem,
    evidence_by_id: dict[str, EvidenceItem],
    *,
    min_overlap_score: float,
) -> CriticFinding:
    referenced_evidence = [
        evidence_by_id[evidence_id]
        for evidence_id in claim.evidence_ids
        if evidence_id in evidence_by_id
    ]
    reasons: list[str] = []
    severity = "info"

    if not claim.evidence_ids:
        reasons.append("missing_evidence_ids")
    if claim.evidence_ids and not referenced_evidence:
        reasons.append("referenced_evidence_not_found")

    evidence_text = " ".join(item.text for item in referenced_evidence)
    overlap_score = _token_overlap_score(claim.claim_text, evidence_text)
    if referenced_evidence and overlap_score < min_overlap_score:
        reasons.append("weak_lexical_support")

    claim_numbers = _numeric_values(claim.claim_text)
    evidence_numbers = set(_numeric_values(evidence_text))
    missing_numbers = [value for value in claim_numbers if value not in evidence_numbers]
    if missing_numbers:
        reasons.append("numeric_value_not_in_evidence")

    if "missing_evidence_ids" in reasons or "referenced_evidence_not_found" in reasons:
        status = "unsupported"
        severity = "fail"
    elif "weak_lexical_support" in reasons or "numeric_value_not_in_evidence" in reasons:
        status = "needs_review"
        severity = "warn"
    else:
        status = "supported"

    return CriticFinding(
        claim_id=claim.claim_id,
        status=status,
        severity=severity,
        reasons=reasons,
        evidence_ids=claim.evidence_ids,
        overlap_score=round(overlap_score, 4),
        numeric_values=claim_numbers,
    )


def _token_overlap_score(claim_text: str, evidence_text: str) -> float:
    claim_tokens = _content_tokens(claim_text)
    if not claim_tokens:
        return 0.0
    evidence_tokens = _content_tokens(evidence_text)
    if not evidence_tokens:
        return 0.0
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in simple_tokenize(text)
        if len(token) > 2 and token not in STOP_WORDS and not token.isdigit()
    }


def _numeric_values(text: str) -> list[str]:
    return re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text)
