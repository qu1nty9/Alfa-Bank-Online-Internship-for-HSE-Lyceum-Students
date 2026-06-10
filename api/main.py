"""FastAPI application for the research assistant MVP."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from research_assistant.audit import AuditEvent, append_audit_event
from research_assistant.config import default_pipeline_config
from research_assistant.collector import build_sources_from_urls, load_seed_sources
from research_assistant.knowledge_graph import build_knowledge_graph
from research_assistant.llm_gateway import default_llm_gateway_metadata
from research_assistant.models import RawDocument, SourceCandidate, SourceType
from research_assistant.parser import parse_raw_documents_safe
from research_assistant.pipeline import run_research_pipeline_with_sources
from research_assistant.planner import is_cltv_topic
from research_assistant.source_discovery import SourceDiscoveryConfig, discover_public_sources
from research_assistant.source_policy import (
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
    uploaded_sources: list[SourceCandidate] | None = None,
    uploaded_file_metadata: list[dict] | None = None,
) -> ResearchRunResponse:
    _require_role(actor_role, "analyst")

    active_run_id = run_id or create_run_id()
    created_at = datetime.now(UTC)
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
    should_discover = not is_cltv_topic(topic) and auto_discover_sources
    if should_discover:
        discovered_sources = discover_public_sources(
            topic,
            config=SourceDiscoveryConfig(
                enabled=True,
                max_sources=discovery_max_sources,
                timeout_seconds=config.discovery_timeout_seconds,
            ),
        )

    sources = [*uploaded_sources, *request_sources, *discovered_sources]
    active_use_live_fetch = use_live_fetch or bool(request_sources) or bool(discovered_sources)
    source_candidates_for_pipeline: list[SourceCandidate] | None
    source_mode: str | None

    if sources:
        source_candidates_for_pipeline = sources
        source_mode = _source_mode_for(
            uploaded_count=len(uploaded_sources),
            request_count=len(request_sources),
            discovered_count=len(discovered_sources),
        )
    elif is_cltv_topic(topic):
        sources = load_seed_sources(config.seed_sources_path)
        source_candidates_for_pipeline = None
        source_mode = None
    else:
        source_candidates_for_pipeline = []
        source_mode = "no_topic_sources"

    request_settings = {
        "use_live_fetch": active_use_live_fetch,
        "fetch_limit": fetch_limit,
        "source_url_count": len(request_sources),
        "uploaded_source_count": len(uploaded_sources),
        "uploaded_files": uploaded_file_metadata,
        "discovered_source_count": len(discovered_sources),
        "auto_discover_sources": auto_discover_sources,
        "discovery_max_sources": discovery_max_sources,
    }
    config = config.model_copy(
        update={
            "use_live_fetch": active_use_live_fetch,
            "auto_discover_sources": False,
        }
    )
    source_policy_config = load_source_policy_config(SOURCE_POLICY_PATH)
    source_policy = summarize_source_policy(
        sources,
        use_live_fetch=active_use_live_fetch,
        fetch_limit=fetch_limit,
        policy=source_policy_config,
    )
    result = run_research_pipeline_with_sources(
        topic,
        config=config,
        source_candidates=source_candidates_for_pipeline,
        source_mode=source_mode,
    )
    model_gateway = result.model_gateway_metadata
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
    return ResearchRunResponse.model_validate(_with_links(metadata))


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
