"""FastAPI application for the research assistant MVP."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from research_assistant.config import default_pipeline_config
from research_assistant.pipeline import run_research_pipeline

from .run_store import (
    RunArtifactNotFoundError,
    RunNotFoundError,
    create_run_id,
    list_run_metadata,
    load_evidence_csv,
    load_evidence_items,
    load_latest_run_id,
    load_report_markdown,
    load_run_metadata,
    save_pipeline_run,
)
from .schemas import (
    EvidenceResponse,
    HealthResponse,
    ReportResponse,
    ResearchRunListResponse,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchRunStatusResponse,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "reports" / "api_runs"

app = FastAPI(
    title="Bank Research Assistant API",
    version="0.1.0",
    description="API-first MVP for running the modular research assistant pipeline.",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return service health."""

    return HealthResponse(status="ok", service="bank-research-assistant")


@app.post("/research/run", response_model=ResearchRunResponse)
def run_research(request: ResearchRunRequest) -> ResearchRunResponse:
    """Run the research pipeline and persist a queryable run record."""

    run_id = create_run_id()
    created_at = datetime.now(UTC)
    config = default_pipeline_config(PROJECT_ROOT).model_copy(
        update={
            "use_live_fetch": request.use_live_fetch,
            "fetch_limit": request.fetch_limit,
        }
    )
    result = run_research_pipeline(request.topic, config)
    completed_at = datetime.now(UTC)

    metadata = save_pipeline_run(
        runs_dir=RUNS_DIR,
        run_id=run_id,
        result=result,
        created_at=created_at,
        completed_at=completed_at,
    )
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
        },
    }
