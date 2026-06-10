"""FastAPI application for the research assistant MVP."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from research_assistant.audit import AuditEvent, append_audit_event
from research_assistant.config import default_pipeline_config
from research_assistant.collector import build_sources_from_urls, load_seed_sources
from research_assistant.llm_gateway import default_llm_gateway_metadata
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

    _require_role(request.actor_role, "analyst")

    run_id = create_run_id()
    created_at = datetime.now(UTC)
    request_sources = build_sources_from_urls(
        [str(url) for url in request.source_urls],
        topic=request.topic,
    )
    config = default_pipeline_config(PROJECT_ROOT).model_copy(
        update={
            "fetch_limit": request.fetch_limit,
            "auto_discover_sources": request.auto_discover_sources,
            "discovery_max_sources": request.discovery_max_sources,
        }
    )
    discovered_sources = []
    if not request_sources and not is_cltv_topic(request.topic) and request.auto_discover_sources:
        discovered_sources = discover_public_sources(
            request.topic,
            config=SourceDiscoveryConfig(
                enabled=True,
                max_sources=request.discovery_max_sources,
                timeout_seconds=config.discovery_timeout_seconds,
            ),
        )
    sources = request_sources or discovered_sources
    use_live_fetch = request.use_live_fetch or bool(sources)
    request_settings = {
        "use_live_fetch": use_live_fetch,
        "fetch_limit": request.fetch_limit,
        "source_url_count": len(request_sources),
        "discovered_source_count": len(discovered_sources),
        "auto_discover_sources": request.auto_discover_sources,
        "discovery_max_sources": request.discovery_max_sources,
    }
    config = config.model_copy(
        update={
            "use_live_fetch": use_live_fetch,
            "auto_discover_sources": False,
        }
    )
    if not sources and is_cltv_topic(request.topic):
        sources = load_seed_sources(config.seed_sources_path)
    source_policy_config = load_source_policy_config(SOURCE_POLICY_PATH)
    source_policy = summarize_source_policy(
        sources,
        use_live_fetch=use_live_fetch,
        fetch_limit=request.fetch_limit,
        policy=source_policy_config,
    )
    result = run_research_pipeline_with_sources(
        request.topic,
        config=config,
        source_candidates=sources
        if (request_sources or discovered_sources or not is_cltv_topic(request.topic))
        else None,
        source_mode="request_sources"
        if request_sources
        else "auto_discovery"
        if discovered_sources
        else "no_topic_sources"
        if not is_cltv_topic(request.topic)
        else None,
    )
    model_gateway = result.model_gateway_metadata
    completed_at = datetime.now(UTC)

    metadata = save_pipeline_run(
        runs_dir=RUNS_DIR,
        run_id=run_id,
        result=result,
        created_at=created_at,
        completed_at=completed_at,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
        request_settings=request_settings,
        source_policy=source_policy,
        model_gateway=model_gateway,
    )
    audit_event = AuditEvent(
        run_id=run_id,
        actor_id=request.actor_id,
        actor_role=request.actor_role,
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
