"""Rule-based research planner for the first CLTV demo."""

from __future__ import annotations

from .models import ResearchPlan, SearchQuery


CLTV_RESEARCH_BLOCKS = [
    "definition_and_business_value",
    "calculation_methods",
    "required_data",
    "banking_use_cases",
    "risks_and_limitations",
    "quality_metrics",
    "vendors_and_solutions",
]


def build_cltv_research_plan(topic: str = "CLTV in foreign banks") -> ResearchPlan:
    """Build a stable first research plan without relying on an LLM."""

    queries = [
        SearchQuery(
            query="customer lifetime value banking use cases",
            research_block="definition_and_business_value",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query="customer lifetime value calculation banking retention probability margin",
            research_block="calculation_methods",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query="bank customer lifetime value data requirements transactions products campaigns",
            research_block="required_data",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query="CLTV next best action banking personalization retention cross sell",
            research_block="banking_use_cases",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query="customer lifetime value banking privacy bias explainability risks",
            research_block="risks_and_limitations",
            geography="global",
            language="en",
        ),
    ]

    return ResearchPlan(topic=topic, blocks=CLTV_RESEARCH_BLOCKS, queries=queries)

