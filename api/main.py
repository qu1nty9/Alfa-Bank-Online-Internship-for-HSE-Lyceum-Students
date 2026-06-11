"""FastAPI application for the research assistant MVP."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from research_assistant.audit import AuditEvent, append_audit_event
from research_assistant.config import default_pipeline_config
from research_assistant.collector import build_sources_from_urls
from research_assistant.knowledge_graph import build_knowledge_graph
from research_assistant.llm_gateway import default_llm_gateway_metadata
from research_assistant.models import RawDocument, SourceCandidate, SourceType
from research_assistant.parser import parse_raw_documents_safe
from research_assistant.pipeline import run_research_pipeline_with_sources
from research_assistant.planner import build_research_plan
from research_assistant.sensitivity import check_query_sensitivity
from research_assistant.source_discovery import SourceDiscoveryConfig, discover_public_sources
from research_assistant.source_policy import (
    filter_sources_by_policy,
    load_source_policy_config,
    save_source_policy_config,
    summarize_source_policy,
)

from .run_store import (
    RunArtifactNotFoundError,
    RunNotFoundError,
    create_run_id,
    list_run_metadata,
    load_evidence_csv,
    load_evidence_items,
    load_claim_items,
    load_latest_run_id,
    load_report_markdown,
    load_run_metadata,
    save_initial_run_metadata,
    save_pipeline_run,
    save_run_metadata,
)
from .schemas import (
    AuditEventsResponse,
    ClaimsResponse,
    EvidenceResponse,
    HealthResponse,
    KnowledgeGraphResponse,
    ReportResponse,
    ResearchRunAcceptedResponse,
    ResearchReviewRequest,
    ResearchReviewResponse,
    ResearchRunListResponse,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchRunStatusResponse,
    SourcePolicyResponse,
    SourcePolicyUpdateRequest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "reports" / "api_runs"
AUDIT_LOG_PATH = PROJECT_ROOT / "reports" / "audit" / "research_runs.jsonl"
SOURCE_POLICY_PATH = PROJECT_ROOT / "config" / "source_policy.json"
UI_DIR = PROJECT_ROOT / "api" / "static"
ALLOWED_UPLOAD_SUFFIXES = {".md", ".txt", ".pdf", ".html", ".htm"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

app = FastAPI(
    title="Bank Research Assistant API",
    version="0.1.0",
    description="API-first MVP for running the modular research assistant pipeline.",
)
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Return the lightweight demo UI."""

    return FileResponse(UI_DIR / "index.html")


@app.get("/ui", include_in_schema=False)
def ui() -> FileResponse:
    """Return the lightweight demo UI."""

    return FileResponse(UI_DIR / "index.html")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service health."""

    return HealthResponse(status="ok", service="bank-research-assistant")


@app.post("/research/run", response_model=ResearchRunResponse)
def run_research(request: ResearchRunRequest) -> ResearchRunResponse:
    """Run the research pipeline and persist a queryable run record."""

    return _run_research_job(
        topic=request.topic,
        use_live_fetch=request.use_live_fetch,
        fetch_limit=request.fetch_limit,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        source_urls=[str(url) for url in request.source_urls],
        auto_discover_sources=request.auto_discover_sources,
        discovery_max_sources=request.discovery_max_sources,
    )


@app.post("/research/run-async", status_code=202, response_model=ResearchRunAcceptedResponse)
def queue_research(
    request: ResearchRunRequest,
    background_tasks: BackgroundTasks,
) -> ResearchRunAcceptedResponse:
    """Queue a research run and return immediately with a status link."""

    _require_role(request.actor_role, "analyst")
    run_id = create_run_id()
    created_at = datetime.now(UTC)
    request_settings = {
        "use_live_fetch": request.use_live_fetch,
        "fetch_limit": request.fetch_limit,
        "source_url_count": len(request.source_urls),
        "uploaded_source_count": 0,
        "uploaded_files": [],
        "discovered_source_count": 0,
        "auto_discover_sources": request.auto_discover_sources,
        "discovery_max_sources": request.discovery_max_sources,
        "execution_mode": "async",
    }
    metadata = _initial_run_metadata(
        run_id=run_id,
        topic=request.topic,
        created_at=created_at,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        request_settings=request_settings,
    )
    save_initial_run_metadata(RUNS_DIR, metadata)

    background_tasks.add_task(
        _execute_queued_research_job,
        run_id,
        created_at.isoformat(),
        request.model_dump(mode="json"),
    )
    linked_metadata = _with_links(metadata)
    return ResearchRunAcceptedResponse(
        run_id=run_id,
        status=metadata["status"],
        created_at=created_at,
        topic=request.topic,
        request_settings=request_settings,
        progress=metadata["progress"],
        links=linked_metadata["links"],
    )


@app.post("/research/run-with-files", response_model=ResearchRunResponse)
async def run_research_with_files(
    topic: str = Form(default="CLTV in foreign banks", min_length=3),
    use_live_fetch: bool = Form(default=False),
    fetch_limit: int | None = Form(default=None, ge=1),
    actor_id: str = Form(default="local_analyst", min_length=3),
    actor_role: str = Form(default="analyst", pattern="^(analyst|reviewer|admin)$"),
    source_urls: str = Form(default=""),
    auto_discover_sources: bool = Form(default=True),
    discovery_max_sources: int = Form(default=8, ge=1, le=20),
    files: list[UploadFile] | None = File(default=None),
) -> ResearchRunResponse:
    """Run research with analyst-uploaded documents as additional sources."""

    run_id = create_run_id()
    config = default_pipeline_config(PROJECT_ROOT).model_copy(
        update={
            "fetch_limit": fetch_limit,
            "auto_discover_sources": auto_discover_sources,
            "discovery_max_sources": discovery_max_sources,
        }
    )
    uploaded_sources, uploaded_file_metadata = await _prepare_uploaded_sources(
        files or [],
        run_id=run_id,
        topic=topic,
        config=config,
    )
    return _run_research_job(
        topic=topic,
        use_live_fetch=use_live_fetch,
        fetch_limit=fetch_limit,
        actor_id=actor_id,
        actor_role=actor_role,
        source_urls=_split_source_urls(source_urls),
        auto_discover_sources=auto_discover_sources,
        discovery_max_sources=discovery_max_sources,
        run_id=run_id,
        uploaded_sources=uploaded_sources,
        uploaded_file_metadata=uploaded_file_metadata,
    )


def _run_research_job(
    *,
    topic: str,
    use_live_fetch: bool,
    fetch_limit: int | None,
    actor_id: str,
    actor_role: str,
    source_urls: list[str],
    auto_discover_sources: bool,
    discovery_max_sources: int,
    run_id: str | None = None,
    created_at: datetime | None = None,
    uploaded_sources: list[SourceCandidate] | None = None,
    uploaded_file_metadata: list[dict] | None = None,
    progress_callback: Any | None = None,
) -> ResearchRunResponse:
    _require_role(actor_role, "analyst")

    active_run_id = run_id or create_run_id()
    created_at = created_at or datetime.now(UTC)
    _record_progress(progress_callback, "accepted", 5, "Run accepted.")
    uploaded_sources = uploaded_sources or []
    uploaded_file_metadata = uploaded_file_metadata or []
    request_sources = build_sources_from_urls(source_urls, topic=topic)
    config_updates = {
        "fetch_limit": fetch_limit,
        "auto_discover_sources": auto_discover_sources,
        "discovery_max_sources": discovery_max_sources,
    }
    if uploaded_sources:
        config_updates.update(
            {
                "min_clean_documents": 1,
                "min_evidence_items": 1,
                "min_evidence_sources": 1,
            }
        )
    config = default_pipeline_config(PROJECT_ROOT).model_copy(update=config_updates)

    discovered_sources: list[SourceCandidate] = []
    sensitivity = check_query_sensitivity(topic)
    if auto_discover_sources and sensitivity.allowed:
        _record_progress(
            progress_callback,
            "discovering_sources",
            20,
            "Discovering public sources.",
        )
        plan = build_research_plan(topic)
        discovered_sources = discover_public_sources(
            topic,
            config=SourceDiscoveryConfig(
                enabled=True,
                max_sources=discovery_max_sources,
                timeout_seconds=config.discovery_timeout_seconds,
            ),
            queries=plan.queries,
        )

    sources = [*uploaded_sources, *request_sources, *discovered_sources]
    source_policy_config = load_source_policy_config(SOURCE_POLICY_PATH)
    allowed_sources = filter_sources_by_policy(sources, source_policy_config)
    allowed_source_ids = {source.source_id for source in allowed_sources}
    allowed_uploaded_count = sum(
        1 for source in uploaded_sources if source.source_id in allowed_source_ids
    )
    allowed_request_count = sum(
        1 for source in request_sources if source.source_id in allowed_source_ids
    )
    allowed_discovered_count = sum(
        1 for source in discovered_sources if source.source_id in allowed_source_ids
    )
    active_use_live_fetch = (
        use_live_fetch or allowed_request_count > 0 or allowed_discovered_count > 0
    )
    _record_progress(
        progress_callback,
        "applying_source_policy",
        35,
        "Applying source policy.",
    )
    source_policy = summarize_source_policy(
        sources,
        use_live_fetch=active_use_live_fetch,
        fetch_limit=fetch_limit,
        policy=source_policy_config,
    )
    source_candidates_for_pipeline: list[SourceCandidate] | None
    source_mode: str | None

    if allowed_sources:
        source_candidates_for_pipeline = allowed_sources
        source_mode = _source_mode_for(
            uploaded_count=allowed_uploaded_count,
            request_count=allowed_request_count,
            discovered_count=allowed_discovered_count,
        )
    else:
        source_candidates_for_pipeline = []
        source_mode = "policy_blocked_sources" if sources else "no_topic_sources"

    request_settings = {
        "use_live_fetch": active_use_live_fetch,
        "requested_live_fetch": use_live_fetch,
        "fetch_limit": fetch_limit,
        "source_url_count": len(request_sources),
        "uploaded_source_count": len(uploaded_sources),
        "uploaded_files": uploaded_file_metadata,
        "discovered_source_count": len(discovered_sources),
        "policy_allowed_source_count": len(allowed_sources),
        "policy_blocked_source_count": len(sources) - len(allowed_sources),
        "auto_discover_sources": auto_discover_sources,
        "discovery_max_sources": discovery_max_sources,
        "execution_mode": "sync" if progress_callback is None else "async",
    }
    config = config.model_copy(
        update={
            "use_live_fetch": active_use_live_fetch,
            "auto_discover_sources": False,
        }
    )
    _record_progress(progress_callback, "running_pipeline", 55, "Running research pipeline.")
    result = run_research_pipeline_with_sources(
        topic,
        config=config,
        source_candidates=source_candidates_for_pipeline,
        source_mode=source_mode,
    )
    if sources and not allowed_sources:
        result.evaluation_summary["source_warning"] = (
            "All candidate sources were blocked by source policy. "
            "Review policy source_decisions, add approved URLs, or loosen the allowlist."
        )
    result.evaluation_summary["source_policy_allowed_count"] = len(allowed_sources)
    result.evaluation_summary["source_policy_blocked_count"] = len(sources) - len(allowed_sources)
    model_gateway = result.model_gateway_metadata
    _record_progress(progress_callback, "persisting_artifacts", 90, "Persisting artifacts.")
    completed_at = datetime.now(UTC)

    metadata = save_pipeline_run(
        runs_dir=RUNS_DIR,
        run_id=active_run_id,
        result=result,
        created_at=created_at,
        completed_at=completed_at,
        actor_id=actor_id,
        actor_role=actor_role,
        request_settings=request_settings,
        source_policy=source_policy,
        model_gateway=model_gateway,
    )
    metadata["progress"] = _progress_payload("completed", 100, "Run completed.")
    audit_event = AuditEvent(
        run_id=active_run_id,
        actor_id=actor_id,
        actor_role=actor_role,
        topic=result.topic,
        status=metadata["status"],
        sensitivity=result.sensitivity.decision,
        quality_gate=result.quality_gate.status,
        request_settings=request_settings,
        source_policy=source_policy,
        model_gateway=model_gateway,
        artifacts=metadata["artifacts"],
    )
    append_audit_event(AUDIT_LOG_PATH, audit_event)
    metadata["audit"] = {
        "logged": True,
        "event_type": audit_event.event_type,
        "log_name": AUDIT_LOG_PATH.name,
    }
    save_run_metadata(RUNS_DIR, metadata)
    _record_progress(progress_callback, "completed", 100, "Run completed.")
    return ResearchRunResponse.model_validate(_with_links(metadata))


def _execute_queued_research_job(
    run_id: str,
    created_at_iso: str,
    request_payload: dict[str, Any],
) -> None:
    """Execute a queued run in a FastAPI background task."""

    def progress_callback(stage: str, percent: int, message: str) -> None:
        _save_run_progress(run_id, stage, percent, message)

    try:
        _run_research_job(
            topic=request_payload["topic"],
            use_live_fetch=bool(request_payload.get("use_live_fetch", False)),
            fetch_limit=request_payload.get("fetch_limit"),
            actor_id=request_payload.get("actor_id", "local_analyst"),
            actor_role=request_payload.get("actor_role", "analyst"),
            source_urls=[str(url) for url in request_payload.get("source_urls", [])],
            auto_discover_sources=bool(request_payload.get("auto_discover_sources", True)),
            discovery_max_sources=int(request_payload.get("discovery_max_sources", 8)),
            run_id=run_id,
            created_at=datetime.fromisoformat(created_at_iso),
            progress_callback=progress_callback,
        )
    except Exception as exc:
        _mark_run_failed(run_id, exc)


def _initial_run_metadata(
    *,
    run_id: str,
    topic: str,
    created_at: datetime,
    actor_id: str,
    actor_role: str,
    request_settings: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "queued",
        "topic": topic,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "created_at": created_at.astimezone(UTC).isoformat(),
        "completed_at": None,
        "sensitivity": "pending",
        "quality_gate": "pending",
        "evaluation_summary": {},
        "request_settings": request_settings,
        "source_policy": {},
        "model_gateway": default_llm_gateway_metadata(),
        "progress": _progress_payload("queued", 0, "Run queued."),
        "review": {
            "status": "not_applicable",
            "updated_at": None,
            "updated_by": None,
            "history": [],
        },
        "audit": {
            "logged": False,
            "event_type": None,
            "log_name": None,
        },
        "artifacts": _empty_artifacts(),
    }


def _empty_artifacts() -> dict[str, None]:
    return {
        "report_markdown": None,
        "claims_csv": None,
        "claims_jsonl": None,
        "evidence_csv": None,
        "evidence_jsonl": None,
        "evaluation_json": None,
    }


def _progress_payload(stage: str, percent: int, message: str) -> dict[str, Any]:
    return {
        "stage": stage,
        "percent": percent,
        "message": message,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _record_progress(
    progress_callback: Any | None,
    stage: str,
    percent: int,
    message: str,
) -> None:
    if progress_callback is None:
        return
    progress_callback(stage, percent, message)


def _save_run_progress(run_id: str, stage: str, percent: int, message: str) -> None:
    try:
        metadata = _with_metadata_defaults(load_run_metadata(RUNS_DIR, run_id))
    except RunNotFoundError:
        return

    metadata["progress"] = _progress_payload(stage, percent, message)
    if stage != "completed":
        metadata["status"] = "running"
        metadata["completed_at"] = None
    save_run_metadata(RUNS_DIR, metadata)


def _mark_run_failed(run_id: str, exc: Exception) -> None:
    try:
        metadata = _with_metadata_defaults(load_run_metadata(RUNS_DIR, run_id))
    except RunNotFoundError:
        return

    error = f"{type(exc).__name__}: {str(exc)[:300]}"
    metadata["status"] = "failed"
    metadata["completed_at"] = datetime.now(UTC).isoformat()
    metadata["quality_gate"] = "fail"
    metadata["evaluation_summary"] = {
        **metadata.get("evaluation_summary", {}),
        "error": error,
    }
    metadata["progress"] = _progress_payload("failed", 100, error)
    audit_event = AuditEvent(
        event_type="research_run.failed",
        run_id=run_id,
        actor_id=metadata["actor_id"],
        actor_role=metadata["actor_role"],
        topic=metadata["topic"],
        status=metadata["status"],
        sensitivity=metadata["sensitivity"],
        quality_gate=metadata["quality_gate"],
        request_settings=metadata["request_settings"],
        source_policy=metadata["source_policy"],
        model_gateway=metadata["model_gateway"],
        artifacts=metadata["artifacts"],
    )
    append_audit_event(AUDIT_LOG_PATH, audit_event)
    metadata["audit"] = {
        "logged": True,
        "event_type": audit_event.event_type,
        "log_name": AUDIT_LOG_PATH.name,
    }
    save_run_metadata(RUNS_DIR, metadata)


async def _prepare_uploaded_sources(
    files: list[UploadFile],
    *,
    run_id: str,
    topic: str,
    config,
) -> tuple[list[SourceCandidate], list[dict]]:
    sources: list[SourceCandidate] = []
    raw_documents: list[RawDocument] = []
    metadata: list[dict] = []
    raw_upload_dir = config.raw_dir / "uploads" / run_id

    for index, upload in enumerate(files, start=1):
        original_name = Path(upload.filename or f"document_{index}.txt").name
        suffix = Path(original_name).suffix.lower() or ".txt"
        if suffix not in ALLOWED_UPLOAD_SUFFIXES:
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Unsupported file type '{suffix}'. "
                    f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_SUFFIXES))}"
                ),
            )

        body = await upload.read()
        if not body:
            raise HTTPException(status_code=400, detail=f"Uploaded file is empty: {original_name}")
        if len(body) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Uploaded file is too large: {original_name}",
            )

        source_id = f"upload_{run_id.rsplit('_', 1)[-1]}_{index:03d}"
        safe_name = _safe_upload_name(original_name)
        raw_path = raw_upload_dir / f"{source_id}_{safe_name}"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(body)

        source = SourceCandidate(
            source_id=source_id,
            url=f"https://local.upload/{run_id}/{quote(safe_name)}",
            title=original_name,
            source_type=SourceType.UPLOADED_DOCUMENT,
            publisher="local upload",
            research_block="definition_and_context",
            language=None,
            status="ready",
            notes="Analyst-uploaded document for local knowledge-base scan.",
        )
        raw_document = RawDocument(
            source_id=source_id,
            url=source.url,
            path=raw_path,
            content_type=_upload_content_type(upload.content_type, suffix),
            from_cache=False,
        )
        sources.append(source)
        raw_documents.append(raw_document)
        metadata.append(
            {
                "source_id": source_id,
                "filename": original_name,
                "content_type": raw_document.content_type,
                "size_bytes": len(body),
            }
        )

    if not raw_documents:
        return [], []

    parse_results = parse_raw_documents_safe(raw_documents, sources, config.clean_dir)
    successful_source_ids = {
        result.source_id for result in parse_results if result.ok and result.clean_document
    }
    for item in metadata:
        item["parsed"] = item["source_id"] in successful_source_ids

    return [
        source for source in sources if source.source_id in successful_source_ids
    ], metadata


def _source_mode_for(
    *,
    uploaded_count: int,
    request_count: int,
    discovered_count: int,
) -> str:
    active_modes = [
        name
        for count, name in [
            (uploaded_count, "uploaded_documents"),
            (request_count, "request_sources"),
            (discovered_count, "auto_discovery"),
        ]
        if count
    ]
    if len(active_modes) == 1:
        return active_modes[0]
    return "mixed_sources"


def _split_source_urls(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


def _safe_upload_name(filename: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in filename)
    return cleaned[:120] or "document.txt"


def _upload_content_type(content_type: str | None, suffix: str) -> str:
    if content_type:
        return content_type
    return {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".pdf": "application/pdf",
        ".html": "text/html",
        ".htm": "text/html",
    }.get(suffix, "application/octet-stream")


@app.get("/research/runs", response_model=ResearchRunListResponse)
def list_research_runs() -> ResearchRunListResponse:
    """Return stored API run metadata."""

    return ResearchRunListResponse(
        runs=[
            ResearchRunStatusResponse.model_validate(_with_links(metadata))
            for metadata in list_run_metadata(RUNS_DIR)
        ]
    )


@app.get("/research/runs/{run_id}/status", response_model=ResearchRunStatusResponse)
def get_run_status(run_id: str) -> ResearchRunStatusResponse:
    """Return status and metadata for one stored research run."""

    metadata = _load_metadata_or_404(run_id)
    return ResearchRunStatusResponse.model_validate(_with_links(metadata))


@app.get("/research/runs/{run_id}/report", response_model=ReportResponse)
def get_run_report(run_id: str) -> ReportResponse:
    """Return the Markdown report for one stored research run."""

    _load_metadata_or_404(run_id)
    try:
        markdown = load_report_markdown(RUNS_DIR, run_id)
    except RunArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report artifact not found") from exc
    return ReportResponse(run_id=run_id, markdown=markdown)


@app.get("/research/runs/{run_id}/evidence", response_model=EvidenceResponse)
def get_run_evidence(run_id: str) -> EvidenceResponse:
    """Return structured evidence items for one stored research run."""

    _load_metadata_or_404(run_id)
    try:
        items = load_evidence_items(RUNS_DIR, run_id)
    except RunArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Evidence artifact not found") from exc
    return EvidenceResponse(run_id=run_id, items=items)


@app.get("/research/runs/{run_id}/claims", response_model=ClaimsResponse)
def get_run_claims(run_id: str) -> ClaimsResponse:
    """Return machine-readable claim/evidence links for one stored run."""

    _load_metadata_or_404(run_id)
    try:
        items = load_claim_items(RUNS_DIR, run_id)
    except RunArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Claims artifact not found") from exc
    return ClaimsResponse(run_id=run_id, items=items)


@app.get("/research/runs/{run_id}/graph", response_model=KnowledgeGraphResponse)
def get_run_graph(run_id: str) -> KnowledgeGraphResponse:
    """Return a claim/evidence/source graph for one stored run."""

    _load_metadata_or_404(run_id)
    try:
        evidence_items = load_evidence_items(RUNS_DIR, run_id)
        claim_items = load_claim_items(RUNS_DIR, run_id)
    except RunArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Graph source artifacts not found") from exc
    return KnowledgeGraphResponse(
        run_id=run_id,
        graph=build_knowledge_graph(
            evidence_items=evidence_items,
            claim_items=claim_items,
        ),
    )


@app.post("/research/runs/{run_id}/review", response_model=ResearchReviewResponse)
def review_run_report(run_id: str, request: ResearchReviewRequest) -> ResearchReviewResponse:
    """Move a report through the reviewer workflow."""

    _require_role(request.actor_role, "reviewer")
    metadata = _with_metadata_defaults(_load_metadata_or_404(run_id))
    review = metadata["review"]
    current_status = review.get("status", "draft")

    if current_status == "not_applicable" or not metadata.get("artifacts", {}).get("report_markdown"):
        raise HTTPException(status_code=409, detail="Run has no report to review")

    _validate_review_transition(current_status, request.decision)

    updated_at = datetime.now(UTC).isoformat()
    history_entry = {
        "from_status": current_status,
        "to_status": request.decision,
        "actor_id": request.actor_id,
        "actor_role": request.actor_role,
        "notes": request.notes,
        "created_at": updated_at,
    }
    review["status"] = request.decision
    review["updated_at"] = updated_at
    review["updated_by"] = request.actor_id
    review["history"] = [*review.get("history", []), history_entry]
    metadata["review"] = review

    audit_event = AuditEvent(
        event_type=f"research_run.{request.decision}",
        run_id=run_id,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        topic=metadata["topic"],
        status=metadata["status"],
        sensitivity=metadata["sensitivity"],
        quality_gate=metadata["quality_gate"],
        request_settings={
            "review_decision": request.decision,
            "review_notes": request.notes,
            "previous_review_status": current_status,
        },
        source_policy=metadata["source_policy"],
        model_gateway=metadata["model_gateway"],
        artifacts=metadata["artifacts"],
    )
    append_audit_event(AUDIT_LOG_PATH, audit_event)
    metadata["audit"] = {
        "logged": True,
        "event_type": audit_event.event_type,
        "log_name": AUDIT_LOG_PATH.name,
    }
    save_run_metadata(RUNS_DIR, metadata)

    linked_metadata = _with_links(metadata)
    return ResearchReviewResponse(
        run_id=run_id,
        review=review,
        audit=metadata["audit"],
        links=linked_metadata["links"],
    )


@app.get("/admin/source-policy", response_model=SourcePolicyResponse)
def get_source_policy(actor_id: str, actor_role: str) -> SourcePolicyResponse:
    """Return the current file-backed source allowlist policy."""

    _require_role(actor_role, "admin")
    return SourcePolicyResponse(
        policy=load_source_policy_config(SOURCE_POLICY_PATH),
        audit={
            "logged": False,
            "event_type": None,
            "log_name": None,
            "actor_id": actor_id,
        },
        links={"self": "/admin/source-policy"},
    )


@app.put("/admin/source-policy", response_model=SourcePolicyResponse)
def update_source_policy(request: SourcePolicyUpdateRequest) -> SourcePolicyResponse:
    """Replace the source allowlist policy. This is the Stage 4 admin scenario."""

    _require_role(request.actor_role, "admin")
    save_source_policy_config(SOURCE_POLICY_PATH, request.policy)
    policy_payload = request.policy.model_dump(mode="json")
    audit_event = AuditEvent(
        event_type="source_policy.updated",
        run_id="source_policy",
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        topic="source allowlist policy",
        status="updated",
        sensitivity="not_applicable",
        quality_gate="not_applicable",
        request_settings={
            "policy_version": request.policy.policy_version,
            "allowed_source_id_count": len(request.policy.allowed_source_ids),
            "allowed_domain_count": len(request.policy.allowed_domains),
        },
        source_policy=policy_payload,
        model_gateway=default_llm_gateway_metadata(),
        artifacts={"source_policy_json": SOURCE_POLICY_PATH.name},
    )
    append_audit_event(AUDIT_LOG_PATH, audit_event)
    return SourcePolicyResponse(
        policy=request.policy,
        audit={
            "logged": True,
            "event_type": audit_event.event_type,
            "log_name": AUDIT_LOG_PATH.name,
            "actor_id": request.actor_id,
        },
        links={"self": "/admin/source-policy"},
    )


@app.get("/admin/audit-events", response_model=AuditEventsResponse)
def get_audit_events(
    actor_id: str,
    actor_role: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> AuditEventsResponse:
    """Return the latest audit events for the demo UI."""

    _require_role(actor_role, "admin")
    events = _load_audit_events(AUDIT_LOG_PATH, limit)
    return AuditEventsResponse(
        actor_id=actor_id,
        count=len(events),
        items=events,
        links={"self": "/admin/audit-events"},
    )


@app.get("/research/report", response_class=PlainTextResponse)
def get_latest_report() -> str:
    """Return the latest generated Markdown report for quick demos."""

    try:
        return load_report_markdown(RUNS_DIR, load_latest_run_id(RUNS_DIR))
    except (RunNotFoundError, RunArtifactNotFoundError):
        pass

    report_path = PROJECT_ROOT / "reports" / "report_cltv.md"
    if not report_path.exists():
        return "No generated report found. Run POST /research/run first."
    return report_path.read_text(encoding="utf-8")


@app.get("/research/evidence", response_class=PlainTextResponse)
def get_latest_evidence_csv() -> str:
    """Return the latest generated evidence CSV for quick demos."""

    try:
        return load_evidence_csv(RUNS_DIR, load_latest_run_id(RUNS_DIR))
    except (RunNotFoundError, RunArtifactNotFoundError):
        pass

    evidence_path = PROJECT_ROOT / "reports" / "evidence_cltv.csv"
    if not evidence_path.exists():
        return "No generated evidence CSV found. Run POST /research/run first."
    return evidence_path.read_text(encoding="utf-8")


def _load_metadata_or_404(run_id: str) -> dict:
    try:
        return load_run_metadata(RUNS_DIR, run_id)
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Research run not found") from exc


def _with_links(metadata: dict) -> dict:
    metadata = _with_metadata_defaults(metadata)
    run_id = metadata["run_id"]
    return {
        **metadata,
        "links": {
            "status": f"/research/runs/{run_id}/status",
            "report": f"/research/runs/{run_id}/report"
            if metadata.get("artifacts", {}).get("report_markdown")
            else None,
            "evidence": f"/research/runs/{run_id}/evidence"
            if metadata.get("artifacts", {}).get("evidence_jsonl")
            else None,
            "claims": f"/research/runs/{run_id}/claims"
            if metadata.get("artifacts", {}).get("claims_jsonl")
            else None,
            "graph": f"/research/runs/{run_id}/graph"
            if metadata.get("artifacts", {}).get("claims_jsonl")
            and metadata.get("artifacts", {}).get("evidence_jsonl")
            else None,
            "review": f"/research/runs/{run_id}/review"
            if metadata.get("artifacts", {}).get("report_markdown")
            else None,
        },
    }


def _with_metadata_defaults(metadata: dict) -> dict:
    return {
        "actor_id": "unknown",
        "actor_role": "analyst",
        "request_settings": {},
        "source_policy": {},
        "model_gateway": {
            "mode": "unknown",
            "provider": None,
            "model": None,
            "external_llm_calls": None,
        },
        "progress": {},
        "review": {
            "status": "not_applicable",
            "updated_at": None,
            "updated_by": None,
            "history": [],
        },
        "audit": {
            "logged": False,
            "event_type": None,
            "log_name": None,
        },
        "artifacts": _empty_artifacts(),
        **metadata,
    }


def _require_role(actual_role: str, required_role: str) -> None:
    if actual_role != required_role:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{required_role}' is required for this action",
        )


def _validate_review_transition(current_status: str, decision: str) -> None:
    allowed_transitions = {
        "draft": {"reviewed"},
        "reviewed": {"approved", "rejected"},
        "approved": set(),
        "rejected": set(),
    }
    if decision not in allowed_transitions.get(current_status, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move report review from '{current_status}' to '{decision}'",
        )


def _load_audit_events(log_path: Path, limit: int) -> list[dict]:
    if not log_path.exists():
        return []

    events: list[dict] = []
    lines = log_path.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
