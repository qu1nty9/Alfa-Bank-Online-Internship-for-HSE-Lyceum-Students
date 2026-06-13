"""Template-based Markdown report generation for evidence-first drafts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .claims import build_claim_items
from .language import ReportLanguage, detect_report_language
from .models import ClaimItem, EvidenceItem

SECTION_TITLES_RU = {
    "definition_and_business_value": "Зачем банкам CLTV",
    "calculation_methods": "Как считают CLTV",
    "required_data": "Какие данные нужны",
    "banking_use_cases": "Как применяют CLTV в банках",
    "risks_and_limitations": "Риски и ограничения",
    "definition_and_context": "Определение и контекст",
    "use_cases_and_examples": "Сценарии применения и примеры",
    "methods_and_approaches": "Методы и подходы",
    "data_and_requirements": "Данные и требования",
    "implementation_considerations": "Практическое внедрение",
}

SECTION_TITLES_EN = {
    "definition_and_business_value": "Why CLTV matters for banks",
    "calculation_methods": "How CLTV is calculated",
    "required_data": "Required data",
    "banking_use_cases": "How banks use CLTV",
    "risks_and_limitations": "Risks and limitations",
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
    language: ReportLanguage | None = None,
) -> str:
    """Render a transparent evidence-first draft report without LLM synthesis."""

    report_language = language or detect_report_language(topic)
    claims = (
        claim_items
        if claim_items is not None
        else build_claim_items(evidence_items, topic=topic, language=report_language)
    )
    lines: list[str] = [f"# {topic}", ""]
    lines.extend(
        _render_short_answer(topic, evidence_items, claims, evaluation_summary, report_language)
    )
    lines.extend(_render_result_passport(evidence_items, evaluation_summary, report_language))

    if llm_synthesis_markdown:
        lines.extend(
            [
                "## LLM synthesis draft",
                "",
                llm_synthesis_markdown.strip(),
                "",
                _llm_synthesis_note(report_language),
                "",
            ]
        )

    lines.extend(_render_full_source_report(evidence_items, evaluation_summary, report_language))

    evidence_by_block = _group_evidence_by_block(evidence_items)
    report_blocks = _ordered_report_blocks(evidence_by_block, evaluation_summary)
    lines.extend([_thematic_heading(report_language), ""])
    for block in report_blocks:
        title = _section_title(block, report_language)
        lines.extend([f"### {title}", ""])
        block_items = evidence_by_block.get(block, [])
        if not block_items:
            lines.extend(
                [
                    _empty_block_note(report_language),
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
                    f"  {_source_label(report_language)}: {item.title or item.source_id} ({item.url})",
                ]
            )
        lines.append("")

    lines.extend(
        [
            _claims_heading(report_language),
            "",
            _claims_intro(report_language),
            "",
            "| claim_id | research_block | evidence_ids | confidence/status | claim_text |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for item in claims:
        lines.append(
            "| "
            f"{item.claim_id} | "
            f"{item.research_block or ''} | "
            f"{', '.join(item.evidence_ids)} | "
            f"{item.confidence} / {item.status} | "
            f"{_escape_table(item.claim_text)} |"
        )
    lines.append("")
    lines.extend(_render_critic_summary(evaluation_summary, report_language))

    lines.extend(
        [
            "## Knowledge graph links",
            "",
            _knowledge_graph_intro(report_language),
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
        lines.append(_source_coverage_line(source_id, blocks, report_language))
    lines.append("")

    lines.extend(
        [
            "## Evidence table",
            "",
            "| rank | source_id | source_type | research_block | relevance_score | trust_score | title |",
            "| --- | --- | --- | --- | --- | --- | --- |",
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
            f"{item.trust_score if item.trust_score is not None else ''} | "
            f"{_escape_table(item.title or '')} |"
        )

    lines.extend(
        [
            "",
            "## Unknowns",
            "",
            *_unknown_bullets(report_language),
            "",
            _recommendations_heading(report_language),
            "",
            *_recommendation_bullets(report_language),
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


def _section_title(block: str, language: ReportLanguage) -> str:
    titles = SECTION_TITLES_RU if language == "ru" else SECTION_TITLES_EN
    return titles.get(block, _humanize_block(block))


def _llm_synthesis_note(language: ReportLanguage) -> str:
    if language == "ru":
        return (
            "Этот блок сгенерирован через LLM Gateway и должен проверяться "
            "по claim/evidence таблицам ниже."
        )
    return (
        "This block was generated through the LLM Gateway and must be checked "
        "against the claim/evidence tables below."
    )


def _thematic_heading(language: ReportLanguage) -> str:
    return "## Тематический разбор" if language == "ru" else "## Thematic analysis"


def _empty_block_note(language: ReportLanguage) -> str:
    if language == "ru":
        return "В текущем evidence-наборе недостаточно подтвержденных фрагментов для этого блока."
    return "The current evidence set does not contain enough confirmed fragments for this block."


def _source_label(language: ReportLanguage) -> str:
    return "Источник" if language == "ru" else "Source"


def _source_type_label(language: ReportLanguage) -> str:
    return "Тип" if language == "ru" else "Type"


def _claims_heading(language: ReportLanguage) -> str:
    return "## Утверждения и доказательства" if language == "ru" else "## Claims and evidence"


def _claims_intro(language: ReportLanguage) -> str:
    if language == "ru":
        return (
            "Каждое утверждение ниже связано с конкретными evidence-фрагментами. "
            "Если evidence_ids пустые или confidence низкий, вывод нельзя использовать "
            "без ручной проверки."
        )
    return (
        "Each claim below is linked to concrete evidence fragments. If evidence_ids are "
        "empty or confidence is low, the conclusion must not be used without manual review."
    )


def _knowledge_graph_intro(language: ReportLanguage) -> str:
    if language == "ru":
        return (
            "Этот слой переносит идею persistent research wiki в MVP: источники остаются "
            "source of truth, а claims и evidence становятся явными связанными узлами для "
            "проверки и повторного использования."
        )
    return (
        "This layer brings the persistent research wiki idea into the MVP: sources remain "
        "the source of truth, while claims and evidence become explicit linked nodes for "
        "review and reuse."
    )


def _source_coverage_line(
    source_id: str,
    blocks: list[str],
    language: ReportLanguage,
) -> str:
    if language == "ru":
        return f"- `{source_id}` связан с блоками: {', '.join(blocks)}."
    return f"- `{source_id}` is linked to blocks: {', '.join(blocks)}."


def _unknown_bullets(language: ReportLanguage) -> list[str]:
    if language == "ru":
        return [
            "- Часть публичных или пользовательских источников могла не загрузиться из-за timeout, SSL или ограничений сайта.",
            "- Evidence зависит от качества auto discovery, source URLs, uploads или подключенного Search/RSS connector.",
            "- Hybrid BM25 ranking использует лексическое совпадение и source trust, но может пропускать семантически близкие фрагменты.",
            "- Текущий отчет является template-based черновиком, а не финальной LLM-сводкой.",
            "- Claim critic выполняет детерминированную первичную проверку, но ручной review аналитика остается обязательным.",
        ]
    return [
        "- Some public or user-provided sources may have failed to load because of timeouts, SSL errors, or website restrictions.",
        "- Evidence quality depends on auto discovery, source URLs, uploads, or the connected Search/RSS connector.",
        "- Hybrid BM25 ranking uses lexical matching and source trust, but can miss semantically related fragments.",
        "- The current report is a template-based draft, not a final LLM-written synthesis.",
        "- The claim critic performs a deterministic first pass, but analyst review remains mandatory.",
    ]


def _recommendations_heading(language: ReportLanguage) -> str:
    if language == "ru":
        return "## Рекомендации для дальнейшей проверки"
    return "## Recommended next checks"


def _recommendation_bullets(language: ReportLanguage) -> list[str]:
    if language == "ru":
        return [
            "- Ручно проверить top evidence по каждому разделу.",
            "- Дозагрузить источники, которые не прошли fetching.",
            "- Добавить LLM Synthesizer только после фиксации quality gate.",
            "- Сравнить текущий hybrid baseline с embeddings/reranker на той же evidence table.",
        ]
    return [
        "- Manually review the top evidence for each section.",
        "- Add or retry sources that failed during fetching.",
        "- Enable the LLM synthesizer only after the quality gate is stable.",
        "- Compare the current hybrid baseline with embeddings or a reranker on the same evidence table.",
    ]


def _unused_source_note(language: ReportLanguage) -> str:
    if language == "ru":
        return (
            "Этот источник был найден или передан в pipeline, но не дал итоговых "
            "evidence-фрагментов после фильтрации и ранжирования."
        )
    return (
        "This source was discovered or provided to the pipeline, but did not produce final "
        "evidence fragments after filtering and ranking."
    )


def _group_evidence_by_block(evidence_items: list[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in evidence_items:
        grouped[item.research_block or "unknown"].append(item)
    return dict(grouped)


def _render_short_answer(
    topic: str,
    evidence_items: list[EvidenceItem],
    claims: list[ClaimItem],
    evaluation_summary: dict[str, Any],
    language: ReportLanguage,
) -> list[str]:
    lines = [
        "## Краткий ответ" if language == "ru" else "## Short answer",
        "",
    ]
    if not evidence_items:
        if language == "ru":
            no_evidence_lines = [
                (
                    "По найденным источникам пока нельзя сформировать надежный бизнес-вывод: "
                    "система не получила достаточный набор evidence-фрагментов по теме."
                ),
                "",
                "Что нужно сделать дальше:",
                "",
                "- добавить публичные source URLs или загрузить локальные документы;",
                "- включить public source discovery, если доступен интернет;",
                "- повторить запуск и проверить quality gate.",
                "",
            ]
        else:
            no_evidence_lines = [
                (
                    "The system cannot produce a reliable business conclusion from the current "
                    "source set because it did not collect enough evidence fragments for the topic."
                ),
                "",
                "Next steps:",
                "",
                "- add public source URLs or upload local documents;",
                "- enable public source discovery when internet access is available;",
                "- rerun the pipeline and review the quality gate.",
                "",
            ]
        lines.extend(
            no_evidence_lines
        )
        return lines

    if language == "ru":
        found_summary = (
            f"По теме `{topic}` найдено {len(evidence_items)} evidence-фрагментов "
            f"из {evaluation_summary.get('evidence_source_count', 0)} источников. "
            "Ниже перечислены главные предварительные выводы; каждый из них связан "
            "с evidence_ids и должен быть проверен аналитиком перед использованием."
        )
        closing_note = (
            "Короткий ответ отражает только найденные и отфильтрованные материалы, "
            "а не внешнее знание модели."
        )
    else:
        found_summary = (
            f"For `{topic}`, the system found {len(evidence_items)} evidence fragments "
            f"from {evaluation_summary.get('evidence_source_count', 0)} sources. "
            "The main preliminary conclusions are listed below; each conclusion is linked "
            "to evidence_ids and should be reviewed by an analyst before use."
        )
        closing_note = (
            "The short answer reflects only the discovered and filtered materials, "
            "not external model knowledge."
        )

    lines.extend(
        [
            found_summary,
            "",
        ]
    )
    for claim in claims[:5]:
        lines.append(
            "- "
            f"{_humanize_block(claim.research_block or 'general')}: "
            f"{_claim_takeaway(claim.claim_text)} "
            f"[confidence: {claim.confidence}; evidence: {', '.join(claim.evidence_ids)}]"
        )
    lines.extend(
        [
            "",
            closing_note,
            "",
        ]
    )
    return lines


def _render_result_passport(
    evidence_items: list[EvidenceItem],
    evaluation_summary: dict[str, Any],
    language: ReportLanguage,
) -> list[str]:
    interpretability = evaluation_summary.get("interpretability_summary", {})
    critic_summary = evaluation_summary.get("critic_summary", {})
    missing_blocks = interpretability.get("weakest_or_missing_blocks") or []
    strongest_blocks = interpretability.get("strongest_supported_blocks") or []
    if language == "ru":
        return [
            "## Паспорт результата",
            "",
            f"- Clean-документов: {evaluation_summary.get('clean_document_count', 0)}.",
            f"- Evidence-фрагментов: {len(evidence_items)}.",
            f"- Источников с evidence: {evaluation_summary.get('evidence_source_count', 0)}.",
            f"- Разнообразие источников: {interpretability.get('source_diversity', 'unknown')}.",
            f"- Покрытие типов источников: {evaluation_summary.get('source_type_coverage', {})}.",
            f"- Самые сильные блоки: {strongest_blocks or 'нет данных'}.",
            f"- Слабые или непокрытые блоки: {missing_blocks or 'нет явных пропусков'}.",
            f"- Ranking mode: {evaluation_summary.get('ranking_mode', 'bm25')}.",
            f"- Claim critic: {critic_summary.get('status', 'not_run')}.",
            f"- Claims needing review: {critic_summary.get('needs_review_claim_count', 0)}.",
            "",
        ]

    return [
        "## Result passport",
        "",
        f"- Clean documents: {evaluation_summary.get('clean_document_count', 0)}.",
        f"- Evidence fragments: {len(evidence_items)}.",
        f"- Sources with evidence: {evaluation_summary.get('evidence_source_count', 0)}.",
        f"- Source diversity: {interpretability.get('source_diversity', 'unknown')}.",
        f"- Source type coverage: {evaluation_summary.get('source_type_coverage', {})}.",
        f"- Strongest supported blocks: {strongest_blocks or 'no data'}.",
        f"- Weak or missing blocks: {missing_blocks or 'no explicit gaps'}.",
        f"- Ranking mode: {evaluation_summary.get('ranking_mode', 'bm25')}.",
        f"- Claim critic: {critic_summary.get('status', 'not_run')}.",
        f"- Claims needing review: {critic_summary.get('needs_review_claim_count', 0)}.",
        "",
    ]


def _render_critic_summary(
    evaluation_summary: dict[str, Any],
    language: ReportLanguage,
) -> list[str]:
    critic_summary = evaluation_summary.get("critic_summary") or {}
    findings = critic_summary.get("findings") or []
    lines = [
        "## Проверка утверждений" if language == "ru" else "## Claim checks",
        "",
        f"- Critic status: `{critic_summary.get('status', 'not_run')}`.",
        f"- Supported claims: {critic_summary.get('supported_claim_count', 0)}.",
        f"- Claims needing review: {critic_summary.get('needs_review_claim_count', 0)}.",
        f"- Unsupported claims: {critic_summary.get('unsupported_claim_count', 0)}.",
        f"- Numeric warnings: {critic_summary.get('numeric_warning_count', 0)}.",
        "",
    ]
    if not findings:
        if language == "ru":
            lines.extend(["Claim critic findings отсутствуют.", ""])
        else:
            lines.extend(["No claim critic findings were recorded.", ""])
        return lines

    lines.extend(
        [
            "| claim_id | status | severity | overlap_score | reasons |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        lines.append(
            "| "
            f"{finding.get('claim_id', '')} | "
            f"{finding.get('status', '')} | "
            f"{finding.get('severity', '')} | "
            f"{finding.get('overlap_score', '')} | "
            f"{_escape_table(', '.join(finding.get('reasons') or []))} |"
        )
    lines.append("")
    return lines


def _render_full_source_report(
    evidence_items: list[EvidenceItem],
    evaluation_summary: dict[str, Any],
    language: ReportLanguage,
) -> list[str]:
    evidence_by_source = _group_evidence_by_source(evidence_items)
    analyzed_sources = evaluation_summary.get("analyzed_sources") or _fallback_sources(
        evidence_items
    )
    if language == "ru":
        lines = [
            "## Полный отчет по источникам и ресурсам",
            "",
            (
                "В этом разделе перечислены найденные или переданные источники, их статус "
                "обработки и evidence-фрагменты, которые реально повлияли на отчет."
            ),
            "",
        ]
    else:
        lines = [
            "## Full source report",
            "",
            (
                "This section lists the discovered or user-provided sources, their processing "
                "status, and the evidence fragments that actually influenced the report."
            ),
            "",
        ]
    if not analyzed_sources:
        if language == "ru":
            lines.extend(["Источники для анализа отсутствуют.", ""])
        else:
            lines.extend(["No sources were available for analysis.", ""])
        return lines

    for source in analyzed_sources:
        source_id = source.get("source_id", "unknown")
        source_evidence = evidence_by_source.get(source_id, [])
        lines.extend(
            [
                f"### {source.get('title') or source_id}",
                "",
                f"- Source ID: `{source_id}`.",
                f"- {_source_type_label(language)}: `{source.get('source_type') or 'unknown'}`.",
                f"- Publisher: {source.get('publisher') or 'unknown'}.",
                f"- Research block: `{source.get('research_block') or 'unknown'}`.",
                f"- Clean text available: {source.get('clean_text_available', False)}.",
                f"- Evidence items used: {source.get('evidence_item_count', len(source_evidence))}.",
                f"- URL: {source.get('url') or 'not available'}.",
                "",
            ]
        )
        if not source_evidence:
            lines.extend(
                [
                    _unused_source_note(language),
                    "",
                ]
            )
            continue

        for item in source_evidence:
            lines.extend(
                [
                    (
                        f"- Evidence `{item.source_id}/{item.chunk_id}` "
                        f"(score: {item.relevance_score or 'n/a'}, block: "
                        f"{item.research_block or 'unknown'}): {_preview(item.text)}"
                    ),
                    f"  Link: {item.url}",
                ]
            )
        lines.append("")
    return lines


def _group_evidence_by_source(evidence_items: list[EvidenceItem]) -> dict[str, list[EvidenceItem]]:
    grouped: dict[str, list[EvidenceItem]] = defaultdict(list)
    for item in evidence_items:
        grouped[item.source_id].append(item)
    return dict(grouped)


def _fallback_sources(evidence_items: list[EvidenceItem]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for item in evidence_items:
        sources[item.source_id] = {
            "source_id": item.source_id,
            "title": item.title,
            "url": str(item.url) if item.url else None,
            "source_type": item.source_type.value,
            "publisher": None,
            "research_block": item.research_block,
            "clean_text_available": True,
            "evidence_item_count": len(
                [
                    evidence
                    for evidence in evidence_items
                    if evidence.source_id == item.source_id
                ]
            ),
        }
    return list(sources.values())


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


def _claim_takeaway(claim_text: str) -> str:
    if ":" in claim_text:
        return claim_text.split(":", 1)[1].strip()
    return claim_text.strip()


def _humanize_block(block: str) -> str:
    return block.replace("_", " ").strip().capitalize()


def _preview(text: str, *, max_chars: int = 280) -> str:
    compact_text = " ".join(text.split())
    if len(compact_text) <= max_chars:
        return compact_text
    return compact_text[: max_chars - 3].rstrip() + "..."


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|")
