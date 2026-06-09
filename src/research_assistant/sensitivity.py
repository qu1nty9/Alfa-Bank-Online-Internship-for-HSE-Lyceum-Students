"""Rule-based sensitivity checks for public research queries."""

from __future__ import annotations

import re

from pydantic import BaseModel


class SensitivityFinding(BaseModel):
    """One sensitivity signal found in a user query."""

    kind: str
    severity: str
    detail: str


class SensitivityResult(BaseModel):
    """Final query-safety decision."""

    decision: str
    findings: list[SensitivityFinding]

    @property
    def allowed(self) -> bool:
        return self.decision != "block"


BLOCKING_PATTERNS = {
    "email": re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b"),
    "phone": re.compile(r"(?:\+?\d[\s()-]?){10,}"),
    "long_number": re.compile(r"\b\d{12,}\b"),
}

WARNING_KEYWORDS = {
    "client database": "Potential internal/client data reference.",
    "customer database": "Potential internal/client data reference.",
    "internal project": "Potential internal project reference.",
    "bank strategy": "Potential internal strategy reference.",
    "scoring model": "Potential model-risk/internal scoring reference.",
    "лимиты": "Potential internal banking limits reference.",
    "клиентская база": "Potential client data reference.",
    "внутренний проект": "Potential internal project reference.",
    "стратегия банка": "Potential internal strategy reference.",
    "скоринг": "Potential scoring-model reference.",
}


def check_query_sensitivity(query: str) -> SensitivityResult:
    """Classify whether a research query is safe to use for public-source search."""

    findings: list[SensitivityFinding] = []
    for kind, pattern in BLOCKING_PATTERNS.items():
        if pattern.search(query):
            findings.append(
                SensitivityFinding(
                    kind=kind,
                    severity="high",
                    detail=f"Query contains a {kind}-like pattern.",
                )
            )

    lower_query = query.lower()
    for keyword, detail in WARNING_KEYWORDS.items():
        if keyword in lower_query:
            findings.append(
                SensitivityFinding(
                    kind="keyword",
                    severity="medium",
                    detail=f"{detail} Keyword: {keyword}",
                )
            )

    if any(finding.severity == "high" for finding in findings):
        decision = "block"
    elif findings:
        decision = "warn"
    else:
        decision = "allow"

    return SensitivityResult(decision=decision, findings=findings)
