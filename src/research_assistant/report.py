"""Template-based Markdown report generation for evidence-first drafts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .claims import build_claim_items
from .models import ClaimItem, EvidenceItem

SECTION_TITLES = {
    "definition_and_business_value": "Зачем банкам CLTV",
    "calculation_methods": "Как считают CLTV",
    "required_data": "Какие данные нужны",
    "banking_use_cases": "Как применяют CLTV в банках",
    "risks_and_limitations": "Риски и ограничения",
    "definition_and_context": "Definition and context",
    "use_cases_and_examples": "Use cases and examples",
    "methods_and_approaches": "Methods and approaches",
    "data_and_requirements": "Data and requirements",
    "implementation_considerations": "Implementation considerations",
}


def render_markdown_report(
    *,
    topic: str,
    evidence_items: list[EvidenceItem],
    evaluation_summary: dict[str, Any],
    claim_items: list[ClaimItem] | None = None,
    llm_synthesis_markdown: str | None = None,
) -> str:
    """Render a transparent evidence-first draft report without LLM synthesis."""

    claims = (
        claim_items
        if claim_items is not None
        else build_claim_items(evidence_items, topic=topic)
    )
    lines: list[str] = [
        f"# {topic}",
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

    if llm_synthesis_markdown:
        lines.extend(
            [
                "## LLM synthesis draft",
                "",
                llm_synthesis_markdown.strip(),
                "",
                (
                    "Этот блок сгенерирован через LLM Gateway и должен проверяться "
                    "по claim/evidence таблицам ниже."
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Claim traceability",
            "",
            "| claim_id | research_block | evidence_ids | confidence | claim_text |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in claims:
        lines.append(
            "| "
            f"{item.claim_id} | "
            f"{item.research_block or ''} | "
            f"{', '.join(item.evidence_ids)} | "
            f"{item.confidence} | "
            f"{_escape_table(item.claim_text)} |"
        )
    lines.append("")

    lines.extend(
        [
            "## Knowledge graph links",
            "",
            (
                "Этот слой переносит идею persistent research wiki в MVP: "
                "источники остаются source of truth, а claims и evidence становятся "
                "явными связанными узлами для проверки и повторного использования."
            ),
            "",
            "| claim_id | supported_by_evidence | source_ids |",
            "| --- | --- | --- |",
        ]
    )
    for item in claims:
        lines.append(
            "| "
            f"{item.claim_id} | "
            f"{', '.join(item.evidence_ids)} | "
            f"{', '.join(item.source_ids)} |"
        )
    lines.extend(["", "### Source coverage", ""])
    for source_id, blocks in _source_block_links(evidence_items).items():
        lines.append(f"- `{source_id}` связан с блоками: {', '.join(blocks)}.")
    lines.append("")

    evidence_by_block = _group_evidence_by_block(evidence_items)
    report_blocks = _ordered_report_blocks(evidence_by_block, evaluation_summary)
    for block in report_blocks:
        title = SECTION_TITLES.get(block, _humanize_block(block))
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
            "- Для произвольных тем evidence зависит от качества auto discovery, source URLs или подключенного Search/RSS connector.",
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


def _ordered_report_blocks(
    evidence_by_block: dict[str, list[EvidenceItem]],
    evaluation_summary: dict[str, Any],
) -> list[str]:
    required_blocks = evaluation_summary.get("required_blocks") or []
    blocks = list(required_blocks)
    for block in evidence_by_block:
        if block not in blocks:
            blocks.append(block)
    return blocks or ["definition_and_context", "risks_and_limitations"]


def _source_block_links(evidence_items: list[EvidenceItem]) -> dict[str, list[str]]:
    links: dict[str, set[str]] = defaultdict(set)
    for item in evidence_items:
        links[item.source_id].add(item.research_block or "unknown")
    return {source_id: sorted(blocks) for source_id, blocks in sorted(links.items())}


def _humanize_block(block: str) -> str:
    return block.replace("_", " ").strip().capitalize()


def _preview(text: str, *, max_chars: int = 280) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[: max_chars - 3].rstrip() + "..."


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")
