"""File-based storage for API research runs."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from research_assistant.pipeline import PipelineResult

LATEST_RUN_FILENAME = "latest_run.json"
METADATA_FILENAME = "metadata.json"

_RUN_ID_RE = re.compile(r"^run_[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}$")


class RunNotFoundError(Exception):
    """Raised when a stored API run cannot be found."""


class RunArtifactNotFoundError(Exception):
    """Raised when a stored API run exists but an artifact is missing."""


def create_run_id(now: datetime | None = None) -> str:
    """Create a sortable, path-safe run id."""

    current_time = now or datetime.now(UTC)
    timestamp = current_time.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{uuid4().hex[:8]}"


def save_pipeline_run(
    *,
    runs_dir: Path,
    run_id: str,
    result: PipelineResult,
    created_at: datetime,
    completed_at: datetime,
    actor_id: str,
    actor_role: str,
    request_settings: dict[str, Any],
    source_policy: dict[str, Any],
    model_gateway: dict[str, Any],
) -> dict[str, Any]:
    """Persist metadata and copy generated artifacts for one pipeline run."""

    run_dir = _run_dir(runs_dir, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    artifacts = {
        "report_markdown": _copy_artifact(result.report_path, run_dir / "report.md"),
        "claims_csv": _copy_artifact(result.claims_csv_path, run_dir / "claims.csv"),
        "claims_jsonl": _copy_artifact(result.claims_jsonl_path, run_dir / "claims.jsonl"),
        "evidence_csv": _copy_artifact(result.evidence_csv_path, run_dir / "evidence.csv"),
        "evidence_jsonl": _copy_artifact(result.evidence_jsonl_path, run_dir / "evidence.jsonl"),
        "evaluation_json": _copy_artifact(result.evaluation_json_path, run_dir / "evaluation.json"),
    }
    metadata: dict[str, Any] = {
        "run_id": run_id,
        "status": "completed" if result.sensitivity.allowed else "blocked",
        "topic": result.topic,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "created_at": created_at.astimezone(UTC).isoformat(),
        "completed_at": completed_at.astimezone(UTC).isoformat(),
        "sensitivity": result.sensitivity.decision,
        "quality_gate": result.quality_gate.status,
        "evaluation_summary": result.evaluation_summary,
        "request_settings": request_settings,
        "source_policy": source_policy,
        "model_gateway": model_gateway,
        "review": {
            "status": "draft" if artifacts["report_markdown"] else "not_applicable",
            "updated_at": completed_at.astimezone(UTC).isoformat(),
            "updated_by": None,
            "history": [],
        },
        "audit": {
            "logged": False,
            "event_type": None,
            "log_name": None,
        },
        "artifacts": artifacts,
    }

    _write_json(run_dir / METADATA_FILENAME, metadata)
    _write_json(runs_dir / LATEST_RUN_FILENAME, {"run_id": run_id})
    return metadata


def save_initial_run_metadata(runs_dir: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Create metadata for a queued or running API run before artifacts exist."""

    run_id = metadata.get("run_id")
    if not isinstance(run_id, str):
        raise RunNotFoundError("unknown")
    run_dir = _run_dir(runs_dir, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(run_dir / METADATA_FILENAME, metadata)
    _write_json(runs_dir / LATEST_RUN_FILENAME, {"run_id": run_id})
    return metadata


def load_run_metadata(runs_dir: Path, run_id: str) -> dict[str, Any]:
    """Load metadata for a stored run."""

    metadata_path = _metadata_path(runs_dir, run_id)
    if not metadata_path.exists():
        raise RunNotFoundError(run_id)
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def save_run_metadata(runs_dir: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Overwrite metadata for an existing stored run."""

    run_id = metadata.get("run_id")
    if not isinstance(run_id, str):
        raise RunNotFoundError("unknown")
    metadata_path = _metadata_path(runs_dir, run_id)
    if not metadata_path.exists():
        raise RunNotFoundError(run_id)
    _write_json(metadata_path, metadata)
    return metadata


def load_latest_run_id(runs_dir: Path) -> str:
    """Return the last API run id."""

    latest_path = runs_dir / LATEST_RUN_FILENAME
    if not latest_path.exists():
        raise RunNotFoundError("latest")
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    run_id = payload.get("run_id")
    if not isinstance(run_id, str):
        raise RunNotFoundError("latest")
    return run_id


def list_run_metadata(runs_dir: Path) -> list[dict[str, Any]]:
    """Return known runs sorted from newest to oldest."""

    if not runs_dir.exists():
        return []

    runs: list[dict[str, Any]] = []
    for metadata_path in runs_dir.glob(f"*/{METADATA_FILENAME}"):
        try:
            runs.append(json.loads(metadata_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue

    return sorted(runs, key=lambda item: item.get("created_at", ""), reverse=True)


def load_report_markdown(runs_dir: Path, run_id: str) -> str:
    """Load the Markdown report for a stored run."""

    metadata = load_run_metadata(runs_dir, run_id)
    report_name = metadata.get("artifacts", {}).get("report_markdown")
    if not report_name:
        raise RunArtifactNotFoundError(run_id)
    report_path = _run_dir(runs_dir, run_id) / report_name
    if not report_path.exists():
        raise RunArtifactNotFoundError(run_id)
    return report_path.read_text(encoding="utf-8")


def load_evidence_items(runs_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Load JSON evidence items for a stored run."""

    metadata = load_run_metadata(runs_dir, run_id)
    evidence_name = metadata.get("artifacts", {}).get("evidence_jsonl")
    if not evidence_name:
        raise RunArtifactNotFoundError(run_id)
    evidence_path = _run_dir(runs_dir, run_id) / evidence_name
    if not evidence_path.exists():
        raise RunArtifactNotFoundError(run_id)

    items: list[dict[str, Any]] = []
    with evidence_path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                items.append(json.loads(line))
    return items


def load_claim_items(runs_dir: Path, run_id: str) -> list[dict[str, Any]]:
    """Load JSON claim/evidence traceability items for a stored run."""

    metadata = load_run_metadata(runs_dir, run_id)
    claims_name = metadata.get("artifacts", {}).get("claims_jsonl")
    if not claims_name:
        raise RunArtifactNotFoundError(run_id)
    claims_path = _run_dir(runs_dir, run_id) / claims_name
    if not claims_path.exists():
        raise RunArtifactNotFoundError(run_id)

    items: list[dict[str, Any]] = []
    with claims_path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                items.append(json.loads(line))
    return items


def load_evidence_csv(runs_dir: Path, run_id: str) -> str:
    """Load CSV evidence for a stored run."""

    metadata = load_run_metadata(runs_dir, run_id)
    evidence_name = metadata.get("artifacts", {}).get("evidence_csv")
    if not evidence_name:
        raise RunArtifactNotFoundError(run_id)
    evidence_path = _run_dir(runs_dir, run_id) / evidence_name
    if not evidence_path.exists():
        raise RunArtifactNotFoundError(run_id)
    return evidence_path.read_text(encoding="utf-8")


def _copy_artifact(source_path: Path | None, target_path: Path) -> str | None:
    if source_path is None or not source_path.exists():
        return None
    shutil.copy2(source_path, target_path)
    return target_path.name


def _metadata_path(runs_dir: Path, run_id: str) -> Path:
    return _run_dir(runs_dir, run_id) / METADATA_FILENAME


def _run_dir(runs_dir: Path, run_id: str) -> Path:
    if not _RUN_ID_RE.match(run_id):
        raise RunNotFoundError(run_id)
    return runs_dir / run_id


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
