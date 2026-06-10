"""Public source discovery connectors for arbitrary research topics."""

from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import quote_plus, urlencode, urljoin
from urllib.request import Request, urlopen

from .models import SearchQuery, SourceCandidate, SourceType

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
    include_arxiv: bool = True
    include_crossref: bool = True
    include_searxng: bool = True
    max_queries: int = 6


def discover_public_sources(
    topic: str,
    *,
    config: SourceDiscoveryConfig | None = None,
    queries: list[SearchQuery] | None = None,
) -> list[SourceCandidate]:
    """Discover public sources for a topic through public and optional search endpoints."""

    cfg = config or SourceDiscoveryConfig()
    if not cfg.enabled or cfg.max_sources <= 0:
        return []

    sources: list[SourceCandidate] = []
    search_queries = _discovery_queries(topic, queries, max_queries=cfg.max_queries)
    for query, block in search_queries:
        remaining = cfg.max_sources - len(_deduplicate_sources(sources))
        if remaining <= 0:
            break
        if cfg.include_wikipedia:
            try:
                sources.extend(_discover_wikipedia(query, block, cfg, limit=remaining))
            except Exception:
                pass
        remaining = cfg.max_sources - len(_deduplicate_sources(sources))
        if remaining <= 0:
            break
        if cfg.include_openalex:
            try:
                sources.extend(_discover_openalex(query, block, cfg, limit=remaining))
            except Exception:
                pass
        remaining = cfg.max_sources - len(_deduplicate_sources(sources))
        if remaining <= 0:
            break
        if cfg.include_arxiv:
            try:
                sources.extend(_discover_arxiv(query, block, cfg, limit=remaining))
            except Exception:
                pass
        remaining = cfg.max_sources - len(_deduplicate_sources(sources))
        if remaining <= 0:
            break
        if cfg.include_crossref:
            try:
                sources.extend(_discover_crossref(query, block, cfg, limit=remaining))
            except Exception:
                pass
        remaining = cfg.max_sources - len(_deduplicate_sources(sources))
        if remaining <= 0:
            break
        if cfg.include_searxng:
            try:
                sources.extend(_discover_searxng(query, block, cfg, limit=remaining))
            except Exception:
                pass

    return _renumber_sources(_deduplicate_sources(sources)[: cfg.max_sources])


def _discover_wikipedia(
    query: str,
    research_block: str,
    config: SourceDiscoveryConfig,
    *,
    limit: int,
) -> list[SourceCandidate]:
    params = urlencode(
        {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": min(limit, 3),
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
                source_id=f"wiki_raw_{index:03d}",
                url=f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                title=title,
                source_type=SourceType.ENCYCLOPEDIA,
                publisher="Wikipedia",
                query=query,
                research_block=research_block,
                language="en",
                status="ready",
                notes="Discovered through Wikipedia public API.",
            )
        )
    return sources


def _discover_openalex(
    query: str,
    research_block: str,
    config: SourceDiscoveryConfig,
    *,
    limit: int,
) -> list[SourceCandidate]:
    params = urlencode(
        {
            "search": query,
            "per-page": min(limit, 3),
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
        title = result.get("title") or f"{query} research source"
        if not source_url:
            continue
        sources.append(
            SourceCandidate(
                source_id=f"openalex_raw_{index:03d}",
                url=source_url,
                title=title,
                source_type=SourceType.RESEARCH_INDEX,
                publisher="OpenAlex",
                query=query,
                research_block=research_block,
                language="en",
                status="ready",
                notes="Discovered through OpenAlex public API.",
            )
        )
    return sources


def _discover_arxiv(
    query: str,
    research_block: str,
    config: SourceDiscoveryConfig,
    *,
    limit: int,
) -> list[SourceCandidate]:
    params = urlencode(
        {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": min(limit, 3),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    payload = _load_text(f"https://export.arxiv.org/api/query?{params}", config.timeout_seconds)
    root = ET.fromstring(payload)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    sources: list[SourceCandidate] = []
    for index, entry in enumerate(root.findall("atom:entry", namespace), start=1):
        title = _xml_text(entry.find("atom:title", namespace)) or f"{query} arXiv source"
        url = _xml_text(entry.find("atom:id", namespace))
        if not url:
            continue
        sources.append(
            SourceCandidate(
                source_id=f"arxiv_raw_{index:03d}",
                url=url,
                title=_normalize_space(title),
                source_type=SourceType.ACADEMIC,
                publisher="arXiv",
                query=query,
                research_block=research_block,
                language="en",
                status="ready",
                notes="Discovered through arXiv public API.",
            )
        )
    return sources


def _discover_crossref(
    query: str,
    research_block: str,
    config: SourceDiscoveryConfig,
    *,
    limit: int,
) -> list[SourceCandidate]:
    params = urlencode({"query": query, "rows": min(limit, 3), "sort": "relevance"})
    payload = _load_json(f"https://api.crossref.org/works?{params}", config.timeout_seconds)
    items = payload.get("message", {}).get("items", [])
    sources: list[SourceCandidate] = []
    for index, item in enumerate(items, start=1):
        urls = [item.get("URL"), item.get("resource", {}).get("primary", {}).get("URL")]
        url = next((value for value in urls if value), None)
        title_values = item.get("title") or []
        title = title_values[0] if title_values else f"{query} Crossref source"
        if not url:
            continue
        sources.append(
            SourceCandidate(
                source_id=f"crossref_raw_{index:03d}",
                url=url,
                title=_normalize_space(title),
                source_type=SourceType.ACADEMIC,
                publisher="Crossref",
                query=query,
                research_block=research_block,
                language="en",
                status="ready",
                notes="Discovered through Crossref public API.",
            )
        )
    return sources


def _discover_searxng(
    query: str,
    research_block: str,
    config: SourceDiscoveryConfig,
    *,
    limit: int,
) -> list[SourceCandidate]:
    endpoint = os.environ.get("SEARXNG_BASE_URL") or os.environ.get("SEARCH_API_ENDPOINT")
    if not endpoint:
        return []
    params = urlencode({"q": query, "format": "json", "language": "en", "safesearch": 1})
    payload = _load_json(urljoin(endpoint.rstrip("/") + "/", f"search?{params}"), config.timeout_seconds)
    results = payload.get("results", [])
    sources: list[SourceCandidate] = []
    for index, result in enumerate(results[: min(limit, 5)], start=1):
        url = result.get("url")
        title = result.get("title") or f"{query} search result"
        if not url:
            continue
        sources.append(
            SourceCandidate(
                source_id=f"search_raw_{index:03d}",
                url=url,
                title=_normalize_space(title),
                source_type=SourceType.OTHER,
                publisher=result.get("engine") or "Search",
                snippet=result.get("content"),
                query=query,
                research_block=research_block,
                language="en",
                status="ready",
                notes="Discovered through configured SearXNG/search endpoint.",
            )
        )
    return sources


def _load_json(url: str, timeout_seconds: int) -> dict:
    return json.loads(_load_text(url, timeout_seconds))


def _load_text(url: str, timeout_seconds: int) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": DEFAULT_DISCOVERY_USER_AGENT,
            "Accept": "application/json, application/atom+xml, text/xml;q=0.9, */*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def _discovery_queries(
    topic: str,
    queries: list[SearchQuery] | None,
    *,
    max_queries: int,
) -> list[tuple[str, str]]:
    if queries:
        planned = [(query.query, query.research_block) for query in queries]
    else:
        planned = [
            (topic, "definition_and_context"),
            (f"{topic} official report", "definition_and_context"),
            (f"{topic} methods implementation", "methods_and_approaches"),
            (f"{topic} risks regulation", "risks_and_limitations"),
        ]
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for query, block in planned:
        normalized = _normalize_space(query).lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append((query, block))
    return deduped[:max_queries]


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


def _renumber_sources(sources: list[SourceCandidate]) -> list[SourceCandidate]:
    # Final ids must be URL-unique, not positional: the fetch cache in data/raw
    # and the clean cache in data/clean are keyed by source_id, so a per-request
    # counter would attribute another URL's cached content across runs and topics.
    renumbered: list[SourceCandidate] = []
    for source in sources:
        prefix = source.source_id.split("_raw_", 1)[0]
        url_hash = hashlib.sha256(str(source.url).encode("utf-8")).hexdigest()[:12]
        renumbered.append(
            source.model_copy(update={"source_id": f"{prefix}_{url_hash}"})
        )
    return renumbered


def _xml_text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    return element.text


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
