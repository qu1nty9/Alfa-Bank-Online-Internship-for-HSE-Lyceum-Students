"""End-to-end orchestration for the modular research assistant pipeline."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pydantic import BaseModel

from .chunker import chunk_clean_documents
from .claims import build_claim_items, write_claims_csv, write_claims_jsonl
from .collector import load_seed_sources
from .config import PipelineConfig, default_pipeline_config
from .evidence import build_evidence_items, write_evidence_csv, write_evidence_jsonl
from .evaluation import build_evaluation_summary, write_evaluation_json
from .fetcher import fetch_sources_safe
from .filtering import filter_chunks, rank_chunks_bm25
from .llm_gateway import build_llm_gateway, llm_gateway_config_from_env
from .models import ClaimItem, CleanDocument, FetchResult, ParseResult, SourceCandidate
from .parser import parse_raw_documents_safe
from .planner import build_research_plan, is_cltv_topic
from .quality_gate import QualityGateResult, run_quality_gate
from .report import render_markdown_report, write_markdown_report
from .sensitivity import SensitivityResult, check_query_sensitivity
from .source_discovery import SourceDiscoveryConfig, discover_public_sources


class PipelineResult(BaseModel):
    """Structured result returned by one pipeline run."""

    topic: str
    sensitivity: SensitivityResult
    fetch_results: list[FetchResult]
    parse_results: list[ParseResult]
    evaluation_summary: dict
    quality_gate: QualityGateResult
    model_gateway_metadata: dict = {}
    claim_items: list[ClaimItem] = []
    claims_csv_path: Path | None = None
    claims_jsonl_path: Path | None = None
    evidence_csv_path: Path | None = None
    evidence_jsonl_path: Path | None = None
    evaluation_json_path: Path | None = None
    report_path: Path | None = None


def run_research_pipeline(topic: str, config: PipelineConfig | None = None) -> PipelineResult:
    """Run the reusable research pipeline for a public research topic."""

    return run_research_pipeline_with_sources(topic, config=config)


def run_research_pipeline_with_sources(
    topic: str,
    *,
    config: PipelineConfig | None = None,
    source_candidates: list[SourceCandidate] | None = None,
    source_mode: str | None = None,
) -> PipelineResult:
    """Run the research pipeline with optional user-provided source candidates."""

    cfg = (config or default_pipeline_config()).resolved()
    sensitivity = check_query_sensitivity(topic)
    if not sensitivity.allowed:
        model_gateway_metadata = build_llm_gateway(
            llm_gateway_config_from_env()
        ).metadata().model_dump(mode="json")
        model_gateway_metadata["synthesis_status"] = "blocked_before_synthesis"
        empty_gate = run_quality_gate(
            evidence_items=[],
            evaluation_summary={"clean_document_count": 0, "evidence_source_count": 0},
            report_markdown="",
        )
        return PipelineResult(
            topic=topic,
            sensitivity=sensitivity,
            fetch_results=[],
            parse_results=[],
            evaluation_summary={"blocked": True, "reason": "sensitivity_check"},
            quality_gate=empty_gate,
            model_gateway_metadata=model_gateway_metadata,
        )

    plan = build_research_plan(topic)
    sources, source_mode = _resolve_sources_for_topic(
        topic=topic,
        config=cfg,
        source_candidates=source_candidates,
        source_mode=source_mode,
    )
    fetch_results: list[FetchResult] = []
    parse_results: list[ParseResult] = []
    use_live_fetch = cfg.use_live_fetch or source_mode == "auto_discovery"

    if use_live_fetch:
        fetch_results = fetch_sources_safe(
            sources,
            cfg.raw_dir,
            limit=cfg.fetch_limit,
            timeout_seconds=cfg.fetch_timeout_seconds,
            force=cfg.force_fetch,
        )
        raw_documents = [
            result.raw_document for result in fetch_results if result.ok and result.raw_document
        ]
        parse_results = parse_raw_documents_safe(raw_documents, sources, cfg.clean_dir)

    clean_documents = _load_cached_clean_documents(cfg.clean_dir, sources)
    chunks = chunk_clean_documents(
        clean_documents,
        sources,
        max_chars=cfg.chunk_max_chars,
        overlap_chars=cfg.chunk_overlap_chars,
        min_chars=cfg.chunk_min_chars,
    )
    filtered_chunks = filter_chunks(
        chunks,
        min_chars=cfg.filter_min_chars,
        min_domain_terms=cfg.filter_min_domain_terms,
        domain_terms=_domain_terms_for_plan(topic, plan),
    )
    ranked_chunks = rank_chunks_bm25(
        filtered_chunks,
        plan.queries,
        top_k_per_query=cfg.top_k_per_query,
    )
    evidence_items = build_evidence_items(ranked_chunks, max_items=cfg.max_evidence_items)
    claim_items = build_claim_items(evidence_items, topic=topic)
    model_gateway_metadata, llm_synthesis_markdown = _maybe_synthesize_with_llm(
        topic,
        evidence_items,
    )
    evaluation_summary = build_evaluation_summary(
        plan=plan,
        sources=sources,
        clean_documents=clean_documents,
        chunks=chunks,
        filtered_chunks=filtered_chunks,
        evidence_items=evidence_items,
    )
    evaluation_summary["source_mode"] = source_mode
    evaluation_summary["source_candidate_count"] = len(sources)
    if source_mode == "no_topic_sources":
        evaluation_summary["source_warning"] = (
            "No topic-matched sources were available. Configure source discovery, "
            "provide public source URLs, or connect Search/RSS."
        )
    report_markdown = render_markdown_report(
        topic=topic,
        evidence_items=evidence_items,
        evaluation_summary=evaluation_summary,
        claim_items=claim_items,
        llm_synthesis_markdown=llm_synthesis_markdown,
    )
    quality_gate = run_quality_gate(
        evidence_items=evidence_items,
        evaluation_summary=evaluation_summary,
        report_markdown=report_markdown,
        min_clean_documents=cfg.min_clean_documents,
        min_evidence_items=cfg.min_evidence_items,
        min_evidence_sources=cfg.min_evidence_sources,
    )

    artifact_slug = _topic_slug(topic)
    claims_csv_path = write_claims_csv(claim_items, cfg.reports_dir / f"claims_{artifact_slug}.csv")
    claims_jsonl_path = write_claims_jsonl(
        claim_items,
        cfg.reports_dir / f"claims_{artifact_slug}.jsonl",
    )
    evidence_csv_path = write_evidence_csv(
        evidence_items,
        cfg.reports_dir / f"evidence_{artifact_slug}.csv",
    )
    evidence_jsonl_path = write_evidence_jsonl(
        evidence_items,
        cfg.reports_dir / f"evidence_{artifact_slug}.jsonl",
    )
    evaluation_json_path = write_evaluation_json(
        evaluation_summary,
        cfg.reports_dir / f"evaluation_{artifact_slug}.json",
    )
    report_path = write_markdown_report(
        report_markdown,
        cfg.reports_dir / f"report_{artifact_slug}.md",
    )

    return PipelineResult(
        topic=topic,
        sensitivity=sensitivity,
        fetch_results=fetch_results,
        parse_results=parse_results,
        evaluation_summary=evaluation_summary,
        quality_gate=quality_gate,
        model_gateway_metadata=model_gateway_metadata,
        claim_items=claim_items,
        claims_csv_path=claims_csv_path,
        claims_jsonl_path=claims_jsonl_path,
        evidence_csv_path=evidence_csv_path,
        evidence_jsonl_path=evidence_jsonl_path,
        evaluation_json_path=evaluation_json_path,
        report_path=report_path,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = argparse.ArgumentParser(description="Run the modular research pipeline.")
    parser.add_argument("--topic", default="CLTV in foreign banks")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--live-fetch", action="store_true")
    parser.add_argument("--fetch-limit", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="Print compact JSON summary.")
    args = parser.parse_args(argv)

    config = default_pipeline_config(args.project_root).model_copy(
        update={
            "use_live_fetch": args.live_fetch,
            "fetch_limit": args.fetch_limit,
        }
    )
    result = run_research_pipeline(args.topic, config)

    if args.json:
        print(
            json.dumps(
                {
                    "topic": result.topic,
                    "sensitivity": result.sensitivity.decision,
                    "quality_gate": result.quality_gate.status,
                    "evaluation_summary": result.evaluation_summary,
                    "report_path": str(result.report_path) if result.report_path else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Topic: {result.topic}")
        print(f"Sensitivity: {result.sensitivity.decision}")
        print(f"Quality gate: {result.quality_gate.status}")
        print(f"Clean documents: {result.evaluation_summary.get('clean_document_count', 0)}")
        print(f"Evidence items: {result.evaluation_summary.get('evidence_item_count', 0)}")
        if result.report_path:
            print(f"Report: {result.report_path}")

    return 0 if result.quality_gate.status in {"pass", "warn"} else 1


def _load_cached_clean_documents(
    clean_dir: Path,
    sources,
) -> list[CleanDocument]:
    sources_by_id = {source.source_id: source for source in sources}
    clean_documents: list[CleanDocument] = []
    for clean_path in sorted(clean_dir.glob("*.txt")):
        source = sources_by_id.get(clean_path.stem)
        if source is None:
            continue
        text = clean_path.read_text(encoding="utf-8")
        clean_documents.append(
            CleanDocument(
                source_id=source.source_id,
                title=source.title,
                url=source.url,
                path=clean_path,
                text=text,
                parser_name="cached_clean_text",
                char_count=len(text),
            )
        )
    return clean_documents


def _resolve_sources_for_topic(
    *,
    topic: str,
    config: PipelineConfig,
    source_candidates: list[SourceCandidate] | None,
    source_mode: str | None,
) -> tuple[list[SourceCandidate], str]:
    if source_candidates is not None:
        return source_candidates, source_mode or "request_sources"

    seed_sources = load_seed_sources(config.seed_sources_path)
    if _is_default_cltv_seed(config.seed_sources_path) and not is_cltv_topic(topic):
        discovered_sources = discover_public_sources(
            topic,
            config=SourceDiscoveryConfig(
                enabled=config.auto_discover_sources,
                max_sources=config.discovery_max_sources,
                timeout_seconds=config.discovery_timeout_seconds,
            ),
        )
        if discovered_sources:
            return discovered_sources, "auto_discovery"
        return [], "no_topic_sources"

    return seed_sources, "seed_sources"


def _is_default_cltv_seed(seed_path: Path | None) -> bool:
    if seed_path is None:
        return True
    return seed_path.name == "cltv_sources_template.csv"


def _domain_terms_for_plan(topic: str, plan) -> set[str]:
    stop_words = {
        "and",
        "the",
        "for",
        "with",
        "from",
        "into",
        "what",
        "как",
        "для",
        "или",
        "это",
        "что",
    }
    terms: set[str] = set()
    for value in [topic, *[query.query for query in plan.queries]]:
        terms.update(token for token in re.findall(r"[a-zA-Zа-яА-Я0-9]+", value.lower()) if token not in stop_words)
    if is_cltv_topic(topic):
        terms.update({"bank", "banking", "banks", "customer", "cltv", "clv", "retention"})
    return terms


def _topic_slug(topic: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", topic.lower()).strip("_")
    return slug[:80] or "research"


def _maybe_synthesize_with_llm(
    topic: str,
    evidence_items,
) -> tuple[dict, str | None]:
    gateway = build_llm_gateway(llm_gateway_config_from_env())
    metadata = gateway.metadata().model_dump(mode="json")
    if not metadata["external_llm_calls"]:
        metadata["synthesis_status"] = "not_requested"
        return metadata, None

    try:
        synthesis = gateway.synthesize_report(topic, evidence_items)
    except Exception as exc:
        metadata["synthesis_status"] = "fallback"
        metadata["last_error"] = f"{type(exc).__name__}: {str(exc)[:220]}"
        return metadata, None

    metadata["synthesis_status"] = "success"
    return metadata, synthesis


if __name__ == "__main__":
    raise SystemExit(main())
