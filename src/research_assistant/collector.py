"""Source collectors for curated seed files and user-provided public URLs."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from .models import SourceCandidate, SourceType

REQUIRED_SEED_COLUMNS = {
    "source_id",
    "url",
    "title",
    "source_type",
    "publisher",
    "research_block",
    "language",
    "status",
    "notes",
}


class SeedSourceError(ValueError):
    """Raised when a seed-source CSV cannot be safely loaded."""


def load_seed_sources(path: str | Path, *, include_todo: bool = False) -> list[SourceCandidate]:
    """Load validated source candidates from a curated seed CSV file."""

    csv_path = Path(path)
    if not csv_path.exists():
        raise SeedSourceError(f"Seed source file does not exist: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = REQUIRED_SEED_COLUMNS - fieldnames
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise SeedSourceError(f"Seed source file is missing columns: {missing}")

        sources: list[SourceCandidate] = []
        seen_ids: set[str] = set()
        for row_number, row in enumerate(reader, start=2):
            status = (row.get("status") or "").strip().lower()
            if status == "todo" and not include_todo:
                continue

            source_id = (row.get("source_id") or "").strip()
            if source_id in seen_ids:
                raise SeedSourceError(f"Duplicate source_id at row {row_number}: {source_id}")
            seen_ids.add(source_id)

            try:
                sources.append(_source_candidate_from_row(row))
            except ValidationError as exc:
                raise SeedSourceError(f"Invalid seed source at row {row_number}: {exc}") from exc

    return sources


def group_sources_by_research_block(
    sources: list[SourceCandidate],
) -> dict[str, list[SourceCandidate]]:
    """Group source candidates by their research block."""

    grouped: dict[str, list[SourceCandidate]] = defaultdict(list)
    for source in sources:
        grouped[source.research_block or "unknown"].append(source)
    return dict(grouped)


def build_sources_from_urls(
    urls: list[str],
    *,
    topic: str,
    source_type: SourceType = SourceType.OTHER,
) -> list[SourceCandidate]:
    """Build source candidates from user-provided public URLs."""

    sources: list[SourceCandidate] = []
    for index, raw_url in enumerate(urls, start=1):
        url = raw_url.strip()
        if not url:
            continue
        domain = urlparse(url).netloc.replace("www.", "") or "provided source"
        sources.append(
            SourceCandidate(
                source_id=f"user_{index:03d}",
                url=url,
                title=f"{topic} source {index} ({domain})",
                source_type=source_type,
                publisher=domain,
                research_block="definition_and_context",
                language="en",
                status="ready",
                notes="User-provided public source URL for an arbitrary topic run.",
            )
        )
    return sources


def _source_candidate_from_row(row: dict[str, str]) -> SourceCandidate:
    source_type = _parse_source_type(row.get("source_type", ""))

    return SourceCandidate(
        source_id=(row.get("source_id") or "").strip(),
        url=(row.get("url") or "").strip(),
        title=(row.get("title") or "").strip(),
        source_type=source_type,
        publisher=(row.get("publisher") or "").strip() or None,
        research_block=(row.get("research_block") or "").strip() or None,
        language=(row.get("language") or "").strip() or None,
        status=(row.get("status") or "ready").strip().lower(),
        notes=(row.get("notes") or "").strip() or None,
    )


def _parse_source_type(value: str) -> SourceType:
    normalized = (value or "").strip().lower()
    if not normalized:
        return SourceType.OTHER

    try:
        return SourceType(normalized)
    except ValueError:
        return SourceType.OTHER
