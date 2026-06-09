# FastAPI MVP

Run locally:

```bash
PYTHONPATH=src uvicorn api.main:app --reload
```

Endpoints:

- `GET /health`
- `POST /research/run`
- `GET /research/runs`
- `GET /research/runs/{run_id}/status`
- `GET /research/runs/{run_id}/report`
- `GET /research/runs/{run_id}/evidence`
- `GET /research/report`
- `GET /research/evidence`

Swagger UI:

- `http://127.0.0.1:8000/docs`

## Run contract

`POST /research/run` runs the modular pipeline synchronously and stores an API run under `reports/api_runs/{run_id}/`.

The response includes:

- `run_id` - stable identifier for follow-up requests;
- `status` - `completed` or `blocked`;
- `sensitivity` - query policy decision;
- `quality_gate` - `pass`, `warn`, or `fail`;
- `evaluation_summary` - pipeline metrics;
- `links` - API paths for status, report, and evidence.

The run-specific endpoints should be used by integrations:

```text
GET /research/runs/{run_id}/status
GET /research/runs/{run_id}/report
GET /research/runs/{run_id}/evidence
```

`GET /research/report` and `GET /research/evidence` are kept as quick demo shortcuts for the latest run.
