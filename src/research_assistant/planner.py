"""Rule-based research planners for demo and generic research topics."""

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

GENERIC_RESEARCH_BLOCKS = [
    "definition_and_context",
    "use_cases_and_examples",
    "methods_and_approaches",
    "data_and_requirements",
    "risks_and_limitations",
    "implementation_considerations",
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


def build_generic_research_plan(topic: str) -> ResearchPlan:
    """Build a topic-aware research plan for arbitrary public research topics."""

    clean_topic = topic.strip()
    queries = [
        SearchQuery(
            query=f"{clean_topic} overview official report",
            research_block="definition_and_context",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query=f"{clean_topic} use cases examples case study",
            research_block="use_cases_and_examples",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query=f"{clean_topic} methods framework implementation approach",
            research_block="methods_and_approaches",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query=f"{clean_topic} data requirements metrics inputs",
            research_block="data_and_requirements",
            geography="global",
            language="en",
        ),
        SearchQuery(
            query=f"{clean_topic} risks limitations regulation governance",
            research_block="risks_and_limitations",
            geography="global",
            language="en",
        ),
    ]
    return ResearchPlan(topic=clean_topic, blocks=GENERIC_RESEARCH_BLOCKS, queries=queries)


def build_research_plan(topic: str) -> ResearchPlan:
    """Build the best available research plan for a topic."""

    if is_cltv_topic(topic):
        return build_cltv_research_plan(topic)
    return build_generic_research_plan(topic)


def is_cltv_topic(topic: str) -> bool:
    """Return whether the topic should use the curated CLTV demo plan."""

    normalized_topic = topic.lower()
    return any(term in normalized_topic for term in ("cltv", "clv", "customer lifetime value"))
