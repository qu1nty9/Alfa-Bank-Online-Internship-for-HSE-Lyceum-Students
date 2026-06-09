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
- `GET /research/runs/{run_id}/claims`
- `GET /research/runs/{run_id}/evidence`
- `POST /research/runs/{run_id}/review`
- `GET /research/report`
- `GET /research/evidence`
- `GET /admin/source-policy`
- `PUT /admin/source-policy`

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
- `request_settings` - live-fetch settings used by this run;
- `source_policy` - curated-source policy summary;
- `model_gateway` - model mode and external-call boundary;
- `review` - report review state;
- `audit` - audit log status;
- `links` - API paths for status, report, claims, evidence, and review.

The run-specific endpoints should be used by integrations:

```text
GET /research/runs/{run_id}/status
GET /research/runs/{run_id}/report
GET /research/runs/{run_id}/claims
GET /research/runs/{run_id}/evidence
POST /research/runs/{run_id}/review
```

`GET /research/report` and `GET /research/evidence` are kept as quick demo shortcuts for the latest run.

## Bank-ready metadata

`POST /research/run` accepts optional actor metadata:

```json
{
  "topic": "CLTV in foreign banks",
  "use_live_fetch": false,
  "actor_id": "demo_analyst",
  "actor_role": "analyst"
}
```

Each run appends an audit event to:

```text
reports/audit/research_runs.jsonl
```

The MVP currently uses `OfflineTemplateLLMGateway`, so `model_gateway.external_llm_calls` is `false`.

## Review workflow

The current MVP enforces a simple metadata-based role model:

- `analyst` can run research with `POST /research/run`;
- `reviewer` can move a report through review states;
- `admin` can inspect and update the file-backed source allowlist.

Report review states:

```text
draft -> reviewed -> approved
draft -> reviewed -> rejected
```

Review request example:

```json
{
  "actor_id": "demo_reviewer",
  "actor_role": "reviewer",
  "decision": "reviewed",
  "notes": "Evidence table checked."
}
```

Every review action is appended to `reports/audit/research_runs.jsonl`.

## Source policy admin workflow

The source allowlist lives in:

```text
config/source_policy.json
```

It controls:

- allowed source types;
- explicit seed source ids;
- blocked source ids;
- allowed public domains;
- policy notes shown in run metadata and audit logs.

Read policy as admin:

```bash
curl "http://127.0.0.1:8000/admin/source-policy?actor_id=demo_admin&actor_role=admin"
```

Update policy as admin with a wrapped JSON payload:

```bash
curl -X PUT http://127.0.0.1:8000/admin/source-policy \
  -H "Content-Type: application/json" \
  -d @policy_update.json
```

Example `policy_update.json`:

```json
{
  "actor_id": "demo_admin",
  "actor_role": "admin",
  "policy": {
    "policy_version": "source-policy-v1",
    "mode": "curated_seed_with_optional_live_fetch",
    "allowed_source_types": ["consulting", "academic", "vendor"],
    "allowed_source_ids": ["seed_001"],
    "blocked_source_ids": [],
    "allowed_domains": ["teradata.com"],
    "notes": ["Use curated public sources first."]
  }
}
```

Each update writes `source_policy.updated` to `reports/audit/research_runs.jsonl`.

## LLM Gateway

The codebase has a replaceable gateway contract in `src/research_assistant/llm_gateway.py`.

Supported modes:

- `offline_template` - default, deterministic, no external calls;
- `openai_compatible` - adapter for future corporate/OpenAI-compatible chat-completions endpoints.
- `gigachat` - adapter profile for GigaChat chat endpoint with a pre-issued access token.

Default run metadata:

```json
{
  "mode": "offline_template",
  "provider": "offline",
  "model": "template-report-v1",
  "external_llm_calls": false
}
```

The OpenAI-compatible adapter refuses to call a model unless `external_calls_enabled=true` is configured explicitly.

When external calls are enabled, the pipeline attempts an optional LLM synthesis draft. If the endpoint is unavailable, the run falls back to the deterministic template report and stores `model_gateway.synthesis_status=fallback`.

Gateway config is read from environment variables:

```env
LLM_GATEWAY_MODE=openai_compatible
LLM_PROVIDER=local_qwen
LLM_MODEL=qwen3:1.7b
LLM_ENDPOINT_URL=http://localhost:11434/v1/chat/completions
LLM_EXTERNAL_CALLS_ENABLED=true
```

The same contract supports AlfaGen if it exposes an OpenAI-compatible endpoint:

```env
LLM_GATEWAY_MODE=openai_compatible
LLM_PROVIDER=alfagen
LLM_MODEL=alfagen-default
LLM_ENDPOINT_URL=https://alfagen.example.com/v1/chat/completions
LLM_API_KEY_ENV_VAR=ALFAGEN_API_KEY
LLM_EXTERNAL_CALLS_ENABLED=true
```

See `docs/local_llm.md` for local Qwen3, AlfaGen, and GigaChat setup.

## Claim/evidence traceability

Each completed run stores a machine-readable claim table:

```text
reports/api_runs/{run_id}/claims.jsonl
reports/api_runs/{run_id}/claims.csv
```

`GET /research/runs/{run_id}/claims` returns items with:

- `claim_id`;
- `claim_text`;
- `research_block`;
- `evidence_ids`;
- `source_ids`;
- `confidence`;
- `status`.

The generated Markdown report also includes a `Claim traceability` table before the narrative sections.
