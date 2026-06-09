"""Template-based Markdown report generation for the first MVP."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import EvidenceItem

SECTION_TITLES = {
    "definition_and_business_value": "Зачем банкам CLTV",
    "calculation_methods": "Как считают CLTV",
    "required_data": "Какие данные нужны",
    "banking_use_cases": "Как применяют CLTV в банках",
    "risks_and_limitations": "Риски и ограничения",
}


def render_markdown_report(
    *,
    topic: str,
    evidence_items: list[EvidenceItem],
    evaluation_summary: dict[str, Any],
) -> str:
    """Render a transparent evidence-first draft report without LLM synthesis."""

    lines: list[str] = [
        "# CLTV в иностранных банках",
        "",
        "## Executive summary",
        "",
        (
            "Это первый evidence-first черновик аналитической записки. "
            "Он не делает свободных утверждений от имени модели: каждый пункт ниже "
            "ссылается на найденный evidence-фрагмент и требует финальной проверки аналитиком."
        ),
        "",
        f"- Тема исследования: `{topic}`.",
        f"- Использовано clean-документов: {evaluation_summary.get('clean_document_count', 0)}.",
        f"- Evidence-фрагментов в черновике: {len(evidence_items)}.",
        f"- Покрытие типов источников: {evaluation_summary.get('source_type_coverage', {})}.",
        "",
    ]

    evidence_by_block = _group_evidence_by_block(evidence_items)
    for block, title in SECTION_TITLES.items():
        lines.extend([f"## {title}", ""])
        block_items = evidence_by_block.get(block, [])
        if not block_items:
            lines.extend(
                [
                    "В текущем evidence-наборе недостаточно подтвержденных фрагментов для этого блока.",
                    "",
                ]
            )
            continue

        for item in block_items[:4]:
            lines.extend(
                [
                    (
                        f"- [{item.source_id}/{item.chunk_id}] "
                        f"{_preview(item.text)}"
                    ),
                    f"  Источник: {item.title or item.source_id} ({item.url})",
                ]
            )
        lines.append("")

    lines.extend(
        [
            "## Evidence table",
            "",
            "| rank | source_id | source_type | research_block | relevance_score | title |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in evidence_items:
        lines.append(
            "| "
            f"{item.rank or ''} | "
            f"{item.source_id} | "
            f"{item.source_type.value} | "
            f"{item.research_block or ''} | "
            f"{item.relevance_score or ''} | "
            f"{_escape_table(item.title or '')} |"
        )

    lines.extend(
        [
            "",
            "## Unknowns",
            "",
            "- Часть seed-источников могла не загрузиться из-за timeout, SSL или ограничений сайта.",
            "- BM25 ранжирует по лексическим совпадениям и может пропускать семантически близкие фрагменты.",
            "- Текущий отчет является template-based черновиком, а не финальной LLM-сводкой.",
            "- Citation accuracy пока требует ручной проверки аналитиком.",
            "",
            "## Рекомендации для дальнейшей проверки",
            "",
            "- Ручно проверить top evidence по каждому разделу.",
            "- Дозагрузить источники, которые не прошли fetching.",
            "- Добавить LLM Synthesizer только после фиксации quality gate.",
            "- Сравнить BM25 baseline с embeddings/reranker на той же evidence table.",
            "",
        ]
    )

    return "\n".join(lines)


def write_markdown_report(report_markdown: str, path: str | Path) -> Path:
    """Write a generated Markdown report."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_markdown, encoding="utf-8")
    return output_path


def _group_evidence_by_block(evidence_items: list[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in evidence_items:
        grouped[item.research_block or "unknown"].append(item)
    return dict(grouped)


def _preview(text: str, *, max_chars: int = 280) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[: max_chars - 3].rstrip() + "..."


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")
