"""Source policy configuration and summaries for bank-ready traceability."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from .models import SourceCandidate, SourceType

DEFAULT_ALLOWED_SOURCE_TYPES = [
    SourceType.OFFICIAL_BANK,
    SourceType.REGULATOR,
    SourceType.CONSULTING,
    SourceType.ACADEMIC,
    SourceType.VENDOR,
    SourceType.ENCYCLOPEDIA,
    SourceType.RESEARCH_INDEX,
    SourceType.USER_PROVIDED,
    SourceType.UPLOADED_DOCUMENT,
]

DEFAULT_POLICY_NOTES = [
    "Use curated public sources first.",
    "Prefer official banks, regulators, reports, academic sources, and reputable vendors.",
    "Do not position anti-bot bypass as a project capability.",
    "Use live fetching only for public URLs from the curated source list.",
]


class SourcePolicyConfig(BaseModel):
    """File-backed allowlist policy for public research sources."""

    policy_version: str = "source-policy-v1"
    mode: str = "curated_seed_with_optional_live_fetch"
    allowed_source_types: list[SourceType] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_SOURCE_TYPES)
    )
    allow_unlisted_public_sources: bool = True
    allowed_source_ids: list[str] = Field(default_factory=list)
    blocked_source_ids: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: list(DEFAULT_POLICY_NOTES))


def default_source_policy_config() -> SourcePolicyConfig:
    """Return the default source policy used when no config file exists."""

    return SourcePolicyConfig()


def load_source_policy_config(path: str | Path) -> SourcePolicyConfig:
    """Load a source policy config from JSON, or return defaults if it is missing."""

    policy_path = Path(path)
    if not policy_path.exists():
        return default_source_policy_config()
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    return SourcePolicyConfig.model_validate(payload)


def save_source_policy_config(path: str | Path, policy: SourcePolicyConfig) -> Path:
    """Persist a source policy config as formatted JSON."""

    policy_path = Path(path)
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy_path.write_text(
        json.dumps(policy.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return policy_path


def summarize_source_policy(
    sources: list[SourceCandidate],
    *,
    use_live_fetch: bool,
    fetch_limit: int | None,
    policy: SourcePolicyConfig | None = None,
) -> dict[str, Any]:
    """Build an auditable summary of the source boundary for one run."""

    active_policy = policy or default_source_policy_config()
    ready_sources = [source for source in sources if source.status == "ready"]
    allowed_sources = [source for source in ready_sources if _source_is_allowed(source, active_policy)]
    blocked_sources = [
        source for source in sources if source.status != "ready" or source not in allowed_sources
    ]

    return {
        "policy_version": active_policy.policy_version,
        "mode": active_policy.mode,
        "live_fetch_enabled": use_live_fetch,
        "fetch_limit": fetch_limit,
        "candidate_source_count": len(sources),
        "ready_source_count": len(ready_sources),
        "allowed_source_count": len(allowed_sources),
        "blocked_or_deprioritized_source_count": len(blocked_sources),
        "allowed_source_types": sorted(
            source_type.value for source_type in active_policy.allowed_source_types
        ),
        "allow_unlisted_public_sources": active_policy.allow_unlisted_public_sources,
        "allowed_source_id_count": len(active_policy.allowed_source_ids),
        "allowed_domain_count": len(active_policy.allowed_domains),
        "source_type_counts": dict(
            sorted(Counter(source.source_type.value for source in ready_sources).items())
        ),
        "allowed_source_ids": [source.source_id for source in allowed_sources],
        "blocked_source_ids": [source.source_id for source in blocked_sources],
        "configured_blocked_source_ids": list(active_policy.blocked_source_ids),
        "allowed_domains": list(active_policy.allowed_domains),
        "policy_notes": list(active_policy.notes),
    }


def _source_is_allowed(source: SourceCandidate, policy: SourcePolicyConfig) -> bool:
    if source.status != "ready":
        return False
    if source.source_id in set(policy.blocked_source_ids):
        return False
    if source.source_type not in set(policy.allowed_source_types):
        return False
    if (
        policy.allowed_source_ids
        and not policy.allow_unlisted_public_sources
        and source.source_id not in set(policy.allowed_source_ids)
    ):
        return False
    is_unlisted_allowed_source = (
        policy.allow_unlisted_public_sources and source.source_id not in set(policy.allowed_source_ids)
    )
    if (
        policy.allowed_domains
        and not is_unlisted_allowed_source
        and not _domain_is_allowed(_source_domain(source), policy.allowed_domains)
    ):
        return False
    return True


def _source_domain(source: SourceCandidate) -> str:
    return urlparse(str(source.url)).netloc.lower().removeprefix("www.")


def _domain_is_allowed(domain: str, allowed_domains: list[str]) -> bool:
    normalized_allowed_domains = [
        allowed_domain.lower().removeprefix("www.") for allowed_domain in allowed_domains
    ]
    return any(
        domain == allowed_domain or domain.endswith(f".{allowed_domain}")
        for allowed_domain in normalized_allowed_domains
    )
