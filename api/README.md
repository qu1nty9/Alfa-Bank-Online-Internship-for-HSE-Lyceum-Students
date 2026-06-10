# FastAPI MVP

Run locally:

```bash
PYTHONPATH=src uvicorn api.main:app --reload
```

Endpoints:

- `GET /`
- `GET /ui`
- `GET /health`
- `POST /research/run`
- `POST /research/run-with-files`
- `GET /research/runs`
- `GET /research/runs/{run_id}/status`
- `GET /research/runs/{run_id}/report`
- `GET /research/runs/{run_id}/claims`
- `GET /research/runs/{run_id}/evidence`
- `GET /research/runs/{run_id}/graph`
- `POST /research/runs/{run_id}/review`
- `GET /research/report`
- `GET /research/evidence`
- `GET /admin/source-policy`
- `PUT /admin/source-policy`
- `GET /admin/audit-events`

Swagger UI:

- `http://127.0.0.1:8000/docs`

Demo UI:

- `http://127.0.0.1:8000/ui`

## Demo UI

The API serves a lightweight no-build UI from `api/static/`.

Routes:

```text
GET /
GET /ui
GET /static/app.js
GET /static/styles.css
```

The UI is intentionally thin:

- it calls the public FastAPI endpoints;
- it has no Node.js build step;
- it keeps the API as the integration contract;
- it can be replaced by a bank frontend without changing the pipeline.

The current UI has one analyst window:

- topic input;
- plus menu for `.md`, `.txt`, `.pdf`, `.html` uploads;
- optional public source URLs;
- run history on the left;
- compact tabs for result inspection.

UI tabs:

- `Отчёт`;
- `Доказательства`;
- `Утверждения`;
- `Проверка`;
- `Аудит`.

## Run contract

`POST /research/run` runs the modular pipeline synchronously and stores an API run under `reports/api_runs/{run_id}/`.

`POST /research/run-with-files` accepts the same research settings as multipart form data and adds uploaded documents as local sources. Supported file types: `.md`, `.txt`, `.pdf`, `.html`, `.htm`.

For every topic, including CLTV, auto discovery is enabled by default and uses the same public-source flow. You can also pass public `source_urls` to fix or strengthen the source set, or upload local knowledge-base documents. The CLTV seed file is available only as an explicit offline demo fixture; it is not used as a hidden fallback for API runs.

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
- `links` - API paths for status, report, claims, evidence, graph, and review.

The run-specific endpoints should be used by integrations:

```text
GET /research/runs/{run_id}/status
GET /research/runs/{run_id}/report
GET /research/runs/{run_id}/claims
GET /research/runs/{run_id}/evidence
GET /research/runs/{run_id}/graph
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
  "actor_role": "analyst",
  "source_urls": [],
  "auto_discover_sources": true,
  "discovery_max_sources": 8
}
```

Arbitrary topic example:

```json
{
  "topic": "AI fraud detection in insurance",
  "actor_id": "demo_analyst",
  "actor_role": "analyst",
  "auto_discover_sources": true,
  "discovery_max_sources": 8,
  "source_urls": []
}
```

Arbitrary topic with fixed source URLs:

```json
{
  "topic": "AI fraud detection in insurance",
  "actor_id": "demo_analyst",
  "actor_role": "analyst",
  "auto_discover_sources": false,
  "source_urls": [
    "https://example.com/public-report"
  ]
}
```

Arbitrary topic with an uploaded markdown document:

```bash
curl -X POST http://127.0.0.1:8000/research/run-with-files \
  -F "topic=AI fraud detection in insurance" \
  -F "actor_id=demo_analyst" \
  -F "actor_role=analyst" \
  -F "auto_discover_sources=false" \
  -F "files=@./research_note.md;type=text/markdown"
```

Uploaded files are saved under ignored `data/raw/uploads/{run_id}/`, parsed into ignored `data/clean/`, and represented as `source_type=uploaded_document` in policy/evidence metadata.

## Knowledge graph

`GET /research/runs/{run_id}/graph` returns a plain JSON graph:

- `source` nodes;
- `evidence` nodes;
- `claim` nodes;
- `supported_by` edges from claim to evidence;
- `from_source` edges from evidence to source.

This is the lightweight implementation of the persistent research-wiki idea: the raw documents remain source of truth, while reusable links between claims, evidence, and sources become explicit integration artifacts.

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
- explicit source ids, including optional offline demo fixture ids;
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
    "mode": "open_discovery_with_policy_controls",
    "allowed_source_types": ["official_bank", "regulator", "consulting", "academic", "vendor", "encyclopedia", "research_index", "user_provided", "uploaded_document", "news", "other"],
    "allow_unlisted_public_sources": true,
    "allowed_source_ids": [],
    "blocked_source_ids": [],
    "allowed_domains": [],
    "notes": ["Use public discovery connectors, explicit source URLs, or uploaded local documents as source inputs."]
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

The generated Markdown report is structured for business review:

- `Краткий ответ` first;
- `Паспорт результата` with quality/source coverage metadata;
- `Полный отчет по источникам и ресурсам`;
- thematic analysis;
- `Утверждения и доказательства`;
- evidence table and unknowns.
