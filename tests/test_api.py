import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import AUDIT_LOG_PATH, SOURCE_POLICY_PATH, app
from research_assistant.models import FetchResult, RawDocument, SourceCandidate, SourceType


@pytest.fixture(autouse=True)
def fake_public_discovery_and_fetch(monkeypatch) -> None:
    """Keep API tests offline while exercising the auto-discovery path."""

    def fake_discover_public_sources(topic: str, *, config=None, queries=None):
        # Mirror the production contract: discovery returns URL-hash ids,
        # never positional counters (those poisoned the shared fetch cache).
        url = "https://example.com/research-report"
        return [
            SourceCandidate(
                source_id="auto_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:12],
                url=url,
                title=f"{topic} research report",
                source_type=SourceType.RESEARCH_INDEX,
                publisher="Example Research",
                query=queries[0].query if queries else topic,
                research_block="definition_and_context",
                language="en",
                status="ready",
                notes="Offline API test discovery fixture.",
            )
        ]

    def fake_fetch_sources_safe(
        sources,
        raw_dir,
        *,
        limit=None,
        timeout_seconds=20,
        force=False,
    ):
        Path(raw_dir).mkdir(parents=True, exist_ok=True)
        selected_sources = sources[:limit] if limit else sources
        results = []
        for source in selected_sources:
            raw_path = Path(raw_dir) / f"{source.source_id}.html"
            raw_path.write_text(
                (
                    "<main>"
                    f"<h1>{source.title}</h1>"
                    f"<p>{source.title} provides overview, use cases, methods, "
                    "implementation approach, data requirements, metrics, risks, "
                    "limitations, governance, official report context, market analysis, "
                    "and best practices for business analysts in banking and insurance.</p>"
                    "</main>"
                ),
                encoding="utf-8",
            )
            results.append(
                FetchResult(
                    source_id=source.source_id,
                    ok=True,
                    raw_document=RawDocument(
                        source_id=source.source_id,
                        url=source.url,
                        path=raw_path,
                        content_type="text/html",
                        from_cache=False,
                    ),
                )
            )
        return results

    monkeypatch.setattr("api.main.discover_public_sources", fake_discover_public_sources)
    monkeypatch.setattr("research_assistant.pipeline.fetch_sources_safe", fake_fetch_sources_safe)


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_ui_shell_and_static_assets_are_served() -> None:
    client = TestClient(app)

    ui_response = client.get("/ui")
    app_js_response = client.get("/static/app.js")

    assert ui_response.status_code == 200
    assert "text/html" in ui_response.headers["content-type"]
    assert "Bank Research Console" in ui_response.text
    assert "Source URLs" in ui_response.text
    assert "Public search" in ui_response.text
    assert "Upload documents" in ui_response.text
    assert "Claims" in ui_response.text
    assert "markdown-body" in ui_response.text
    assert "/static/app.js" in ui_response.text
    assert app_js_response.status_code == 200
    assert "runResearchWithFiles" in app_js_response.text
    assert "renderMarkdown" in app_js_response.text
    assert "sourceCell" in app_js_response.text


def test_research_run_endpoint_uses_auto_discovery_for_any_topic() -> None:
    client = TestClient(app)

    response = client.post(
        "/research/run",
        json={"topic": "CLTV in foreign banks", "use_live_fetch": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"].startswith("run_")
    assert payload["status"] == "completed"
    assert payload["sensitivity"] == "allow"
    assert payload["quality_gate"] in {"pass", "warn"}
    assert payload["evaluation_summary"]["planner_mode"] == "generic"
    assert payload["evaluation_summary"]["report_language"] == "en"
    assert payload["evaluation_summary"]["source_mode"] == "auto_discovery"
    assert payload["evaluation_summary"]["clean_document_count"] >= 1
    assert payload["request_settings"]["use_live_fetch"] is True
    assert payload["request_settings"]["request_id"]
    assert payload["request_settings"]["discovered_source_count"] == 1
    assert payload["source_policy"]["candidate_source_count"] == 1
    assert payload["source_policy"]["allowed_source_count"] == 1
    assert payload["model_gateway"]["mode"] == "offline_template"
    assert payload["model_gateway"]["provider"] == "offline"
    assert payload["model_gateway"]["model"] == "template-report-v1"
    assert payload["model_gateway"]["api_key_configured"] is False
    assert payload["model_gateway"]["external_llm_calls"] is False
    assert payload["model_gateway"]["synthesis_status"] == "not_requested"
    assert payload["observability"]["request_id"] == payload["request_settings"]["request_id"]
    assert payload["observability"]["total_duration_ms"] >= 0
    assert any(
        event["stage"] == "completed"
        for event in payload["observability"]["stage_events"]
    )
    assert payload["review"]["status"] == "draft"
    assert payload["audit"]["logged"] is True
    assert payload["links"]["status"].endswith("/status")
    assert payload["links"]["report"].endswith("/report")
    assert payload["links"]["evidence"].endswith("/evidence")
    assert payload["links"]["claims"].endswith("/claims")
    assert payload["links"]["graph"].endswith("/graph")
    assert payload["links"]["review"].endswith("/review")


def test_async_research_run_returns_run_id_and_status_link() -> None:
    client = TestClient(app)

    response = client.post(
        "/research/run-async",
        json={"topic": "CLTV in foreign banks", "use_live_fetch": False},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["run_id"].startswith("run_")
    assert payload["status"] == "queued"
    assert payload["progress"]["stage"] == "queued"
    assert payload["links"]["status"].endswith("/status")

    status_response = client.get(payload["links"]["status"])
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["run_id"] == payload["run_id"]
    assert status_payload["status"] in {"queued", "running", "completed", "blocked", "failed"}
    assert "progress" in status_payload


def test_source_policy_blocks_sources_before_pipeline() -> None:
    client = TestClient(app)
    original_policy_text = SOURCE_POLICY_PATH.read_text(encoding="utf-8")
    blocked_url = "https://example.com/research-report"
    blocked_source_id = "auto_" + hashlib.sha256(blocked_url.encode("utf-8")).hexdigest()[:12]

    try:
        policy = json.loads(original_policy_text)
        policy["blocked_source_ids"] = [blocked_source_id]
        SOURCE_POLICY_PATH.write_text(
            json.dumps(policy, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        response = client.post(
            "/research/run",
            json={"topic": "CLTV in foreign banks", "use_live_fetch": False},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["quality_gate"] == "fail"
        assert payload["evaluation_summary"]["source_mode"] == "policy_blocked_sources"
        assert payload["evaluation_summary"]["evidence_item_count"] == 0
        assert payload["request_settings"]["policy_allowed_source_count"] == 0
        assert payload["request_settings"]["policy_blocked_source_count"] == 1
        assert payload["source_policy"]["allowed_source_count"] == 0
        assert payload["source_policy"]["blocked_source_ids"] == [blocked_source_id]
        assert payload["source_policy"]["source_decisions"][0]["reason"] == "source_id_blocked"
    finally:
        SOURCE_POLICY_PATH.write_text(original_policy_text, encoding="utf-8")


def test_research_run_blocks_sensitive_query() -> None:
    client = TestClient(app)

    response = client.post(
        "/research/run",
        json={"topic": "CLTV for ivan@example.com", "use_live_fetch": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"].startswith("run_")
    assert payload["status"] == "blocked"
    assert payload["sensitivity"] == "block"
    assert payload["quality_gate"] == "fail"
    assert payload["review"]["status"] == "not_applicable"
    assert payload["audit"]["logged"] is True


def test_arbitrary_topic_without_sources_returns_no_evidence_instead_of_cltv_report() -> None:
    client = TestClient(app)

    response = client.post(
        "/research/run",
        json={
            "topic": "AI fraud detection in insurance",
            "use_live_fetch": False,
            "auto_discover_sources": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["quality_gate"] == "fail"
    assert payload["evaluation_summary"]["planner_mode"] == "generic"
    assert payload["evaluation_summary"]["source_mode"] == "no_topic_sources"
    assert payload["evaluation_summary"]["evidence_item_count"] == 0
    assert payload["source_policy"]["candidate_source_count"] == 0

    report_response = client.get(payload["links"]["report"])
    assert report_response.status_code == 200
    assert report_response.json()["markdown"].startswith("# AI fraud detection in insurance")


def test_reviewer_cannot_start_research_run() -> None:
    client = TestClient(app)

    response = client.post(
        "/research/run",
        json={
            "topic": "CLTV in foreign banks",
            "actor_id": "test_reviewer",
            "actor_role": "reviewer",
        },
    )

    assert response.status_code == 403


def test_run_specific_report_and_evidence_endpoints_return_payloads() -> None:
    client = TestClient(app)
    run_response = client.post("/research/run", json={"topic": "CLTV in foreign banks"})
    run_id = run_response.json()["run_id"]

    status_response = client.get(f"/research/runs/{run_id}/status")
    report_response = client.get(f"/research/runs/{run_id}/report")
    evidence_response = client.get(f"/research/runs/{run_id}/evidence")
    claims_response = client.get(f"/research/runs/{run_id}/claims")
    graph_response = client.get(f"/research/runs/{run_id}/graph")

    assert status_response.status_code == 200
    assert status_response.json()["run_id"] == run_id
    assert report_response.status_code == 200
    assert "# CLTV" in report_response.json()["markdown"]
    assert "## Short answer" in report_response.json()["markdown"]
    assert "## Full source report" in report_response.json()["markdown"]
    assert "## Claims and evidence" in report_response.json()["markdown"]
    assert "## Knowledge graph links" in report_response.json()["markdown"]
    assert evidence_response.status_code == 200
    evidence_items = evidence_response.json()["items"]
    assert len(evidence_items) >= 1
    assert "source_id" in evidence_items[0]
    assert claims_response.status_code == 200
    claim_items = claims_response.json()["items"]
    assert len(claim_items) >= 1
    assert claim_items[0]["claim_id"].startswith("claim_")
    assert claim_items[0]["evidence_ids"]
    assert graph_response.status_code == 200
    graph = graph_response.json()["graph"]
    assert graph["summary"]["claim_count"] >= 1
    assert graph["summary"]["edge_count"] >= 1


def test_mixed_english_and_russian_topic_returns_russian_report() -> None:
    client = TestClient(app)
    run_response = client.post("/research/run", json={"topic": "CLTV применение в банках"})
    payload = run_response.json()
    run_id = payload["run_id"]

    report_response = client.get(f"/research/runs/{run_id}/report")

    assert run_response.status_code == 200
    assert payload["evaluation_summary"]["report_language"] == "ru"
    assert report_response.status_code == 200
    markdown = report_response.json()["markdown"]
    assert "## Краткий ответ" in markdown
    assert "## Полный отчет по источникам и ресурсам" in markdown
    assert "## Утверждения и доказательства" in markdown


def test_research_run_with_uploaded_markdown_file() -> None:
    client = TestClient(app)
    markdown = """
    # AI fraud detection in insurance

    AI fraud detection in insurance uses anomaly detection, claims history, provider
    behavior, document checks, and transaction signals to prioritize suspicious claims.
    Business analysts compare fraud detection methods by precision, recall, operational
    review cost, explainability, and customer friction. Implementation considerations
    include data quality, model governance, false positives, privacy controls, and audit
    trails for every decision. Insurance teams also need reporting workflows that connect
    each claim about fraud detection to exact evidence from internal policy documents.
    """

    response = client.post(
        "/research/run-with-files",
        data={
            "topic": "AI fraud detection in insurance",
            "actor_id": "test_analyst",
            "actor_role": "analyst",
            "auto_discover_sources": "false",
            "use_live_fetch": "false",
        },
        files={
            "files": (
                "fraud_detection.md",
                markdown.encode("utf-8"),
                "text/markdown",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["quality_gate"] in {"pass", "warn"}
    assert payload["evaluation_summary"]["source_mode"] == "uploaded_documents"
    assert payload["evaluation_summary"]["clean_document_count"] == 1
    assert payload["evaluation_summary"]["evidence_item_count"] >= 1
    assert payload["request_settings"]["uploaded_source_count"] == 1
    assert payload["request_settings"]["uploaded_files"][0]["parsed"] is True
    assert payload["request_settings"]["uploaded_files"][0]["sha256"]
    assert payload["request_settings"]["uploaded_files"][0]["detected_content_type"] == "text/plain"
    assert payload["request_settings"]["uploaded_files"][0]["retention_days"] == 7
    assert payload["source_policy"]["source_type_counts"]["uploaded_document"] == 1

    graph_response = client.get(payload["links"]["graph"])
    assert graph_response.status_code == 200
    graph = graph_response.json()["graph"]
    assert graph["summary"]["source_count"] == 1
    assert graph["summary"]["claim_count"] >= 1


def test_research_run_rejects_disguised_pdf_upload() -> None:
    client = TestClient(app)

    response = client.post(
        "/research/run-with-files",
        data={
            "topic": "AI fraud detection in insurance",
            "actor_id": "test_analyst",
            "actor_role": "analyst",
            "auto_discover_sources": "false",
            "use_live_fetch": "false",
        },
        files={
            "files": (
                "fake.pdf",
                b"not a pdf file",
                "application/pdf",
            )
        },
    )

    assert response.status_code == 415
    assert "Invalid PDF signature" in response.json()["detail"]


def test_report_review_workflow_requires_reviewer_and_valid_transition() -> None:
    client = TestClient(app)
    run_response = client.post(
        "/research/run",
        json={
            "topic": "CLTV in foreign banks",
            "actor_id": "test_analyst",
            "actor_role": "analyst",
        },
    )
    run_id = run_response.json()["run_id"]

    analyst_review_response = client.post(
        f"/research/runs/{run_id}/review",
        json={
            "actor_id": "test_analyst",
            "actor_role": "analyst",
            "decision": "reviewed",
        },
    )
    premature_approval_response = client.post(
        f"/research/runs/{run_id}/review",
        json={
            "actor_id": "test_reviewer",
            "actor_role": "reviewer",
            "decision": "approved",
        },
    )
    reviewed_response = client.post(
        f"/research/runs/{run_id}/review",
        json={
            "actor_id": "test_reviewer",
            "actor_role": "reviewer",
            "decision": "reviewed",
            "notes": "Evidence table checked.",
        },
    )
    approved_response = client.post(
        f"/research/runs/{run_id}/review",
        json={
            "actor_id": "test_reviewer",
            "actor_role": "reviewer",
            "decision": "approved",
            "notes": "Report approved for demo.",
        },
    )
    status_response = client.get(f"/research/runs/{run_id}/status")

    assert analyst_review_response.status_code == 403
    assert premature_approval_response.status_code == 409
    assert reviewed_response.status_code == 200
    assert reviewed_response.json()["review"]["status"] == "reviewed"
    assert approved_response.status_code == 200
    assert approved_response.json()["review"]["status"] == "approved"
    assert len(approved_response.json()["review"]["history"]) == 2
    assert status_response.json()["review"]["status"] == "approved"

    events = [
        json.loads(line)
        for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching_event_types = [
        event["event_type"] for event in events if event["run_id"] == run_id
    ]
    assert "research_run.completed" in matching_event_types
    assert "research_run.reviewed" in matching_event_types
    assert "research_run.approved" in matching_event_types


def test_source_policy_admin_workflow_requires_admin_and_writes_audit() -> None:
    client = TestClient(app)
    original_policy_text = SOURCE_POLICY_PATH.read_text(encoding="utf-8")

    try:
        forbidden_response = client.get(
            "/admin/source-policy",
            params={"actor_id": "test_analyst", "actor_role": "analyst"},
        )
        get_response = client.get(
            "/admin/source-policy",
            params={"actor_id": "test_admin", "actor_role": "admin"},
        )
        policy = get_response.json()["policy"]
        policy["notes"] = [*policy["notes"], "Temporary test note."]

        update_response = client.put(
            "/admin/source-policy",
            json={
                "actor_id": "test_admin",
                "actor_role": "admin",
                "policy": policy,
            },
        )

        assert forbidden_response.status_code == 403
        assert get_response.status_code == 200
        assert get_response.json()["policy"]["allowed_source_ids"]
        assert update_response.status_code == 200
        assert update_response.json()["audit"]["logged"] is True
        assert update_response.json()["audit"]["event_type"] == "source_policy.updated"

        events = [
            json.loads(line)
            for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert any(
            event["event_type"] == "source_policy.updated"
            and event["actor_id"] == "test_admin"
            for event in events
        )
    finally:
        SOURCE_POLICY_PATH.write_text(original_policy_text, encoding="utf-8")


def test_admin_audit_events_endpoint_requires_admin_and_returns_latest_events() -> None:
    client = TestClient(app)
    run_response = client.post(
        "/research/run",
        json={
            "topic": "CLTV in foreign banks",
            "actor_id": "test_analyst",
            "actor_role": "analyst",
        },
    )
    run_id = run_response.json()["run_id"]

    forbidden_response = client.get(
        "/admin/audit-events",
        params={"actor_id": "test_analyst", "actor_role": "analyst"},
    )
    admin_response = client.get(
        "/admin/audit-events",
        params={"actor_id": "test_admin", "actor_role": "admin", "limit": 20},
    )

    assert forbidden_response.status_code == 403
    assert admin_response.status_code == 200
    payload = admin_response.json()
    assert payload["count"] >= 1
    assert any(event["run_id"] == run_id for event in payload["items"])


def test_research_runs_list_contains_completed_run() -> None:
    client = TestClient(app)
    run_response = client.post("/research/run", json={"topic": "CLTV in foreign banks"})
    run_id = run_response.json()["run_id"]

    response = client.get("/research/runs")

    assert response.status_code == 200
    run_ids = [run["run_id"] for run in response.json()["runs"]]
    assert run_id in run_ids


def test_audit_log_contains_research_run_event() -> None:
    client = TestClient(app)
    run_response = client.post(
        "/research/run",
        json={
            "topic": "CLTV in foreign banks",
            "actor_id": "test_analyst",
            "actor_role": "analyst",
        },
    )
    run_id = run_response.json()["run_id"]

    assert AUDIT_LOG_PATH.exists()
    events = [
        json.loads(line)
        for line in AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching_events = [event for event in events if event["run_id"] == run_id]

    assert len(matching_events) == 1
    assert matching_events[0]["actor_id"] == "test_analyst"
    assert matching_events[0]["source_policy"]["allowed_source_count"] >= 1


def test_unknown_run_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/research/runs/run_20990101T000000Z_deadbeef/status")

    assert response.status_code == 404
