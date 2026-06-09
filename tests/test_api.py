from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
    assert payload["links"]["status"].endswith("/status")
    assert payload["links"]["report"].endswith("/report")
    assert payload["links"]["evidence"].endswith("/evidence")


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


def test_run_specific_report_and_evidence_endpoints_return_payloads() -> None:
    client = TestClient(app)
    run_response = client.post("/research/run", json={"topic": "CLTV in foreign banks"})
    run_id = run_response.json()["run_id"]

    status_response = client.get(f"/research/runs/{run_id}/status")
    report_response = client.get(f"/research/runs/{run_id}/report")
    evidence_response = client.get(f"/research/runs/{run_id}/evidence")

    assert status_response.status_code == 200
    assert status_response.json()["run_id"] == run_id
    assert report_response.status_code == 200
    assert "# CLTV" in report_response.json()["markdown"]
    assert evidence_response.status_code == 200
    evidence_items = evidence_response.json()["items"]
    assert len(evidence_items) >= 1
    assert "source_id" in evidence_items[0]


def test_research_runs_list_contains_completed_run() -> None:
    client = TestClient(app)
    run_response = client.post("/research/run", json={"topic": "CLTV in foreign banks"})
    run_id = run_response.json()["run_id"]

    response = client.get("/research/runs")

    assert response.status_code == 200
    run_ids = [run["run_id"] for run in response.json()["runs"]]
    assert run_id in run_ids


def test_unknown_run_returns_404() -> None:
    client = TestClient(app)

    response = client.get("/research/runs/run_20990101T000000Z_deadbeef/status")

    assert response.status_code == 404
