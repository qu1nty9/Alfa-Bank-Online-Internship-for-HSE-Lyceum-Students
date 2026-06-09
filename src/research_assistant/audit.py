"""Append-only audit logging for bank-ready research runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """One immutable event describing a research run."""

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    event_type: str = "research_run.completed"
    run_id: str
    actor_id: str
    actor_role: str
    topic: str
    status: str
    sensitivity: str
    quality_gate: str
    request_settings: dict[str, Any]
    source_policy: dict[str, Any]
    model_gateway: dict[str, Any]
    artifacts: dict[str, str | None]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def append_audit_event(log_path: str | Path, event: AuditEvent) -> Path:
    """Append one event as JSONL and return the log path."""

    output_path = Path(log_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("a", encoding="utf-8") as file:
        payload = event.model_dump(mode="json")
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    return output_path
