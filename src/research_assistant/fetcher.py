"""Fetching utilities with local raw-content caching."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import FetchResult, RawDocument, SourceCandidate

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; AlfaBankResearchAssistantMVP/0.1; "
    "+https://github.com/qu1nty9/Alfa-Bank-Online-Internship-for-HSE-Lyceum-Students)"
)


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched."""


def fetch_source(
    source: SourceCandidate,
    raw_dir: str | Path,
    *,
    timeout_seconds: int = 20,
    force: bool = False,
) -> RawDocument:
    """Fetch one source and save raw bytes under a stable source_id filename."""

    target_path = raw_document_path(source, raw_dir)
    if target_path.exists() and not force:
        return RawDocument(
            source_id=source.source_id,
            url=source.url,
            path=target_path,
            content_type=_guess_content_type_from_path(target_path),
            from_cache=True,
        )

    request = Request(
        str(source.url),
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
            status_code = getattr(response, "status", None)
            content_type = response.headers.get("Content-Type")
    except HTTPError as exc:
        raise FetchError(f"HTTP error for {source.source_id}: {exc.code}") from exc
    except URLError as exc:
        raise FetchError(f"URL error for {source.source_id}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise FetchError(f"Timeout while fetching {source.source_id}") from exc

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(body)

    return RawDocument(
        source_id=source.source_id,
        url=source.url,
        path=target_path,
        content_type=content_type,
        status_code=status_code,
        from_cache=False,
    )


def fetch_sources(
    sources: list[SourceCandidate],
    raw_dir: str | Path,
    *,
    limit: int | None = None,
    timeout_seconds: int = 20,
    force: bool = False,
) -> list[RawDocument]:
    """Fetch several sources sequentially for reproducible notebook demos."""

    selected_sources = sources[:limit] if limit is not None else sources
    return [
        fetch_source(
            source,
            raw_dir,
            timeout_seconds=timeout_seconds,
            force=force,
        )
        for source in selected_sources
    ]


def fetch_sources_safe(
    sources: list[SourceCandidate],
    raw_dir: str | Path,
    *,
    limit: int | None = None,
    timeout_seconds: int = 20,
    force: bool = False,
) -> list[FetchResult]:
    """Fetch several sources and keep going when individual sources fail."""

    selected_sources = sources[:limit] if limit is not None else sources
    results: list[FetchResult] = []
    for source in selected_sources:
        try:
            raw_document = fetch_source(
                source,
                raw_dir,
                timeout_seconds=timeout_seconds,
                force=force,
            )
        except FetchError as exc:
            results.append(FetchResult(source_id=source.source_id, ok=False, error=str(exc)))
        else:
            results.append(
                FetchResult(source_id=source.source_id, ok=True, raw_document=raw_document)
            )
    return results


def raw_document_path(source: SourceCandidate, raw_dir: str | Path) -> Path:
    """Return the stable raw-content path for a source."""

    extension = _extension_from_url(str(source.url))
    safe_source_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", source.source_id)
    return Path(raw_dir) / f"{safe_source_id}{extension}"


def _extension_from_url(url: str) -> str:
    lower_url = url.lower().split("?", 1)[0].split("#", 1)[0]
    if lower_url.endswith(".pdf"):
        return ".pdf"
    if lower_url.endswith(".txt"):
        return ".txt"
    return ".html"


def _guess_content_type_from_path(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "application/pdf"
    if path.suffix.lower() == ".txt":
        return "text/plain"
    return "text/html"
