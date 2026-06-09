# Stage 4 Summary: Bank-Ready Controls

## Статус

Stage 4 закрыт: добавлен первый слой банковской зрелости вокруг API-запусков.

Цель этого шага - не делать production IAM/SSO/БД, а показать контролируемый контур:

- кто запустил исследование;
- какой запрос был отправлен;
- какое policy-решение принято;
- какие источники разрешены source policy;
- какой LLM/model режим использован;
- какие artifacts созданы;
- кто проверил и утвердил отчет;
- какие тезисы отчета связаны с какими evidence items.

## Что добавлено

### Audit log

Каждый `POST /research/run` пишет append-only JSONL event:

```text
reports/audit/research_runs.jsonl
```

Событие содержит:

- `run_id`;
- `actor_id`;
- `actor_role`;
- `topic`;
- `status`;
- `sensitivity`;
- `quality_gate`;
- `request_settings`;
- `source_policy`;
- `model_gateway`;
- `artifacts`.

Review-события также пишутся в этот же log:

- `research_run.reviewed`;
- `research_run.approved`;
- `research_run.rejected`.

### Actor metadata

`POST /research/run` принимает:

- `actor_id`;
- `actor_role`: `analyst`, `reviewer` или `admin`.

В текущем MVP enforced простой role model:

- `analyst` может запускать исследования;
- `reviewer` может переводить отчет по review workflow;
- `admin` может управлять source allowlist через `/admin/source-policy`.

Это не production IAM, а демонстрационный слой банковского контроля поверх API.

### Report review workflow

Каждый успешно созданный отчет получает review state:

```text
draft
```

Reviewer может перевести отчет:

```text
draft -> reviewed -> approved
draft -> reviewed -> rejected
```

Endpoint:

```text
POST /research/runs/{run_id}/review
```

Пример body:

```json
{
  "actor_id": "demo_reviewer",
  "actor_role": "reviewer",
  "decision": "reviewed",
  "notes": "Evidence table checked."
}
```

В `metadata.json` запуска сохраняется:

- текущий `review.status`;
- `updated_by`;
- `updated_at`;
- history всех review actions.

### Claim/evidence traceability

Каждый отчет получает machine-readable claim table:

```text
claims_cltv.csv
claims_cltv.jsonl
```

В API-запуске artifacts копируются в:

```text
reports/api_runs/{run_id}/claims.csv
reports/api_runs/{run_id}/claims.jsonl
```

Endpoint:

```text
GET /research/runs/{run_id}/claims
```

Каждый claim содержит:

- `claim_id`;
- `claim_text`;
- `research_block`;
- `evidence_ids`;
- `source_ids`;
- `confidence`;
- `status`.

Markdown-отчет содержит секцию:

```text
## Claim traceability
```

Это закрывает базовое требование Stage 4: ключевые тезисы должны быть связаны с evidence, а не жить как свободный текст.

### Source policy summary

Source allowlist вынесен из seed CSV в отдельный config:

```text
config/source_policy.json
```

Для каждого запуска сохраняется summary по curated source boundary:

- сколько источников-кандидатов в seed list;
- сколько ready источников;
- сколько источников попадает в разрешенные типы;
- сколько источников попадает в разрешенные source ids и domains;
- source type coverage;
- allowed source ids;
- blocked/deprioritized source ids;
- policy notes.

Текущий принцип:

- сначала curated public sources;
- приоритет official banks, regulators, reports, academic sources, reputable vendors;
- live fetching только по публичным URL из curated list;
- anti-bot bypass не является ценностью проекта.

### Admin source policy workflow

Admin может посмотреть и обновить allowlist:

```text
GET /admin/source-policy
PUT /admin/source-policy
```

Роль enforced на уровне API:

- `analyst` не может менять source policy;
- `reviewer` не может менять source policy;
- `admin` может обновлять policy config.

Каждое обновление пишет audit event:

```text
source_policy.updated
```

### LLM Gateway contract

LLM Gateway оформлен как заменяемый contract в:

```text
src/research_assistant/llm_gateway.py
```

Основные элементы:

- `LLMGatewayConfig`;
- `LLMGatewayMetadata`;
- `OfflineTemplateLLMGateway`;
- `OpenAICompatibleLLMGateway`;
- `GigaChatLLMGateway`;
- `build_llm_gateway`.

По умолчанию используется offline gateway:

```json
{
  "mode": "offline_template",
  "provider": "offline",
  "model": "template-report-v1",
  "external_llm_calls": false
}
```

Это важно для банковского сценария: можно доказать, что MVP не отправляет данные во внешнюю модель.

Gateway читает конфигурацию из env:

```env
LLM_GATEWAY_MODE=openai_compatible
LLM_PROVIDER=local_qwen
LLM_MODEL=qwen3:1.7b
LLM_ENDPOINT_URL=http://localhost:11434/v1/chat/completions
LLM_EXTERNAL_CALLS_ENABLED=true
```

Поддерживаемые профили:

- `offline_template` - дефолт для безопасного демо;
- `local_qwen` - локальный Qwen3-1.7B через Ollama/LM Studio;
- `alfagen` - corporate OpenAI-compatible endpoint;
- `gigachat` - GigaChat endpoint с заранее полученным access token.

OpenAI-compatible/GigaChat adapters не делают внешних вызовов, пока явно не включен `LLM_EXTERNAL_CALLS_ENABLED=true`.

### Architecture diagram

Bank-ready архитектура вынесена в:

```text
docs/architecture.md
```

## Definition of Done

Stage 4 можно считать закрытым, потому что:

1. `POST /research/run` сохраняет actor metadata, source policy, model gateway metadata, artifacts и audit event.
2. Sensitive-запросы блокируются до генерации отчета.
3. Отчет проходит `draft -> reviewed -> approved/rejected`.
4. Claims связаны с evidence ids.
5. Source allowlist хранится в `config/source_policy.json`.
6. Admin-сценарий управления source policy реализован через API.
7. LLM Gateway заменяем между offline, local Qwen, AlfaGen/GigaChat и OpenAI-compatible endpoints.
8. Архитектурная схема подготовлена для финальной защиты.
