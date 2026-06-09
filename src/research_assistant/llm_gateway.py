"""LLM gateway contracts for future model-backed synthesis."""

from __future__ import annotations

from typing import Protocol

from .models import EvidenceItem


class LLMGateway(Protocol):
    """Minimal model interface used by future synthesizers."""

    def synthesize_report(self, topic: str, evidence_items: list[EvidenceItem]) -> str:
        """Generate a report from evidence items."""


class MockLLMGateway:
    """Offline placeholder used until a bank-approved model endpoint is available."""

    def synthesize_report(self, topic: str, evidence_items: list[EvidenceItem]) -> str:
        lines = [
            f"# Mock synthesis for {topic}",
            "",
            "This placeholder does not call an external LLM.",
            f"Evidence items available: {len(evidence_items)}.",
        ]
        return "\n".join(lines)
