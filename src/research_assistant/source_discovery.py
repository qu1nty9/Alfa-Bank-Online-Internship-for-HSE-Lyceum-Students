"""Public source discovery connectors for arbitrary research topics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from .models import SourceCandidate, SourceType

DEFAULT_DISCOVERY_USER_AGENT = (
    "AlfaBankResearchAssistantMVP/0.1 "
    "(https://github.com/qu1nty9/Alfa-Bank-Online-Internship-for-HSE-Lyceum-Students)"
)


@dataclass(frozen=True)
class SourceDiscoveryConfig:
    """Runtime settings for public source discovery."""

    enabled: bool = True
    max_sources: int = 8
    timeout_seconds: int = 12
    include_wikipedia: bool = True
    include_openalex: bool = True


def discover_public_sources(
    topic: str,
    *,
    config: SourceDiscoveryConfig | None = None,
) -> list[SourceCandidate]:
    """Discover public sources for a topic through no-key public endpoints."""

    cfg = config or SourceDiscoveryConfig()
    if not cfg.enabled or cfg.max_sources <= 0:
        return []

    sources: list[SourceCandidate] = []
    if cfg.include_wikipedia:
        try:
            sources.extend(_discover_wikipedia(topic, cfg))
        except Exception:
            pass
    if len(sources) < cfg.max_sources and cfg.include_openalex:
        try:
            sources.extend(_discover_openalex(topic, cfg, offset=len(sources)))
        except Exception:
            pass

    return _deduplicate_sources(sources)[: cfg.max_sources]


def _discover_wikipedia(topic: str, config: SourceDiscoveryConfig) -> list[SourceCandidate]:
    params = urlencode(
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": topic,
            "srlimit": min(config.max_sources, 5),
            "utf8": 1,
        }
    )
    payload = _load_json(f"https://en.wikipedia.org/w/api.php?{params}", config.timeout_seconds)
    results = payload.get("query", {}).get("search", [])
    sources: list[SourceCandidate] = []
    for index, result in enumerate(results, start=1):
        title = result.get("title")
        if not title:
            continue
        sources.append(
            SourceCandidate(
                source_id=f"wiki_{index:03d}",
                url=f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                title=title,
                source_type=SourceType.ENCYCLOPEDIA,
                publisher="Wikipedia",
                research_block="definition_and_context",
                language="en",
                status="ready",
                notes="Discovered through Wikipedia public API.",
            )
        )
    return sources


def _discover_openalex(
    topic: str,
    config: SourceDiscoveryConfig,
    *,
    offset: int,
) -> list[SourceCandidate]:
    params = urlencode(
        {
            "search": topic,
            "per-page": min(config.max_sources, 5),
            "sort": "relevance_score:desc",
        }
    )
    payload = _load_json(f"https://api.openalex.org/works?{params}", config.timeout_seconds)
    results = payload.get("results", [])
    sources: list[SourceCandidate] = []
    for index, result in enumerate(results, start=1):
        source_url = result.get("primary_location", {}).get("landing_page_url") or result.get("doi")
        if not source_url:
            source_url = result.get("id")
        title = result.get("title") or f"{topic} research source"
        if not source_url:
            continue
        sources.append(
            SourceCandidate(
                source_id=f"openalex_{offset + index:03d}",
                url=source_url,
                title=title,
                source_type=SourceType.RESEARCH_INDEX,
                publisher="OpenAlex",
                research_block="methods_and_approaches",
                language="en",
                status="ready",
                notes="Discovered through OpenAlex public API.",
            )
        )
    return sources


def _load_json(url: str, timeout_seconds: int) -> dict:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_DISCOVERY_USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _deduplicate_sources(sources: list[SourceCandidate]) -> list[SourceCandidate]:
    deduped: list[SourceCandidate] = []
    seen_urls: set[str] = set()
    for source in sources:
        url = str(source.url)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(source)
    return deduped
