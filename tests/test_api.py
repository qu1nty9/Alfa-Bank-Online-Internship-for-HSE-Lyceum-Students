import json

from fastapi.testclient import TestClient

from api.main import AUDIT_LOG_PATH, SOURCE_POLICY_PATH, app


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
    assert "Загрузить документы" in ui_response.text
    assert "Утверждения" in ui_response.text
    assert "/static/app.js" in ui_response.text
    assert app_js_response.status_code == 200
    assert "runResearchWithFiles" in app_js_response.text


def test_research_run_endpoint_offline() -> None:
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
    assert payload["evaluation_summary"]["clean_document_count"] >= 5
    assert payload["request_settings"]["use_live_fetch"] is False
    assert payload["source_policy"]["candidate_source_count"] >= 10
    assert payload["source_policy"]["allowed_source_count"] >= 5
    assert payload["model_gateway"]["mode"] == "offline_template"
    assert payload["model_gateway"]["provider"] == "offline"
    assert payload["model_gateway"]["model"] == "template-report-v1"
    assert payload["model_gateway"]["api_key_configured"] is False
    assert payload["model_gateway"]["external_llm_calls"] is False
    assert payload["model_gateway"]["synthesis_status"] == "not_requested"
    assert payload["review"]["status"] == "draft"
    assert payload["audit"]["logged"] is True
    assert payload["links"]["status"].endswith("/status")
    assert payload["links"]["report"].endswith("/report")
    assert payload["links"]["evidence"].endswith("/evidence")
    assert payload["links"]["claims"].endswith("/claims")
    assert payload["links"]["graph"].endswith("/graph")
    assert payload["links"]["review"].endswith("/review")


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
    assert "## Краткий ответ" in report_response.json()["markdown"]
    assert "## Полный отчет по источникам и ресурсам" in report_response.json()["markdown"]
    assert "## Утверждения и доказательства" in report_response.json()["markdown"]
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
    assert payload["source_policy"]["source_type_counts"]["uploaded_document"] == 1

    graph_response = client.get(payload["links"]["graph"])
    assert graph_response.status_code == 200
    graph = graph_response.json()["graph"]
    assert graph["summary"]["source_count"] == 1
    assert graph["summary"]["claim_count"] >= 1


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
    assert matching_events[0]["source_policy"]["allowed_source_count"] >= 5


def test_unknown_run_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/research/runs/run_20990101T000000Z_deadbeef/status")

    assert response.status_code == 404
