# Final Demo Script

## Формат

Цель: показать работающий bank-ready research assistant за 5-7 минут.

Основная тема:

```text
CLTV in foreign banks
```

Дополнительная проверка универсальности:

```text
AI fraud detection in insurance
```

Для произвольной темы auto discovery включен по умолчанию. Публичные source URLs можно добавить вручную, если нужно зафиксировать или усилить набор источников. Если источники не найдены, система должна вернуть `quality_gate=fail`, а не подставить CLTV evidence.

Дополнительный сценарий knowledge-base scan: загрузить `.md`, `.txt`, `.pdf` или `.html` документ через plus menu в UI и получить тот же report/evidence/claims/audit контур по локальному файлу.

Главный тезис демо: система не просто генерирует текст, а строит проверяемый research-конвейер с source policy, evidence, claims, quality gate, review и audit.

## Перед демонстрацией

### 1. Открыть проект

```bash
cd "/Users/yaroslav/Documents/Альфа-Банк_онлайн-практика_лицеистов_НИУ_ВШЭ "
source .venv/bin/activate
```

### 2. Проверить тесты

```bash
.venv/bin/pytest -q
```

Ожидаемо:

```text
40 passed
```

### 3. Выбрать LLM mode

Безопасный default:

```bash
export LLM_GATEWAY_MODE=offline_template
export LLM_PROVIDER=offline
export LLM_MODEL=template-report-v1
export LLM_EXTERNAL_CALLS_ENABLED=false
```

Local Qwen demo:

```bash
export LLM_GATEWAY_MODE=openai_compatible
export LLM_PROVIDER=local_qwen
export LLM_MODEL=qwen3:1.7b
export LLM_ENDPOINT_URL=http://localhost:11434/v1/chat/completions
export LLM_EXTERNAL_CALLS_ENABLED=true
```

Если Ollama на macOS требует явный runtime path, в отдельном терминале:

```bash
export OLLAMA_LIBRARY_PATH=/Applications/Ollama.app/Contents/Resources
/usr/local/bin/ollama serve
```

### 4. Запустить API

```bash
PYTHONPATH=.:src uvicorn api.main:app --reload
```

Открыть Swagger:

```text
http://127.0.0.1:8000/docs
```

Открыть demo UI:

```text
http://127.0.0.1:8000/ui
```

## Demo Flow

### Шаг 1. Health check

В UI:

```text
OpenAPI -> GET /health
```

Endpoint:

```text
GET /health
```

Что сказать:

> API запущен как интегрируемый сервис. Это важно для open-source и будущей интеграции с любым frontend или корпоративной системой.

### Шаг 2. Показать source policy

Endpoint:

```text
GET /admin/source-policy
```

Query params:

```json
{
  "actor_id": "demo_admin",
  "actor_role": "admin"
}
```

Что показать:

- `policy_version`;
- `allowed_source_types`;
- `allowed_source_ids`;
- `allowed_domains`.

Что сказать:

> Система работает не с произвольным web scraping, а с контролируемым allowlist публичных источников. Admin может менять границы источников, и это попадет в audit.

### Шаг 3. Запустить research run

В UI:

```text
Введите тему -> Запустить
```

Endpoint:

```text
POST /research/run
```

Body:

```json
{
  "topic": "CLTV in foreign banks",
  "use_live_fetch": false,
  "actor_id": "demo_analyst",
  "actor_role": "analyst"
}
```

Что показать в response:

- `run_id`;
- `status`;
- `sensitivity`;
- `quality_gate`;
- `source_policy.allowed_source_count`;
- `model_gateway.provider`;
- `model_gateway.synthesis_status`;
- links на report/evidence/claims/review.

Что сказать:

> Один запуск фиксирует actor, request settings, source policy, model gateway metadata и artifacts. Это уже audit-friendly контур.

### Шаг 4. Открыть report

В UI:

```text
Report tab
```

Endpoint:

```text
GET /research/runs/{run_id}/report
```

Что показать:

- `Executive summary`;
- `Claim traceability`;
- `Evidence table`;
- `Unknowns`;
- `Quality notes`.

Что сказать:

> Отчет не является свободным ответом модели. Он связан с evidence и содержит неизвестные, которые нужно проверить дальше.

### Шаг 5. Открыть evidence

В UI:

```text
Evidence tab
```

Endpoint:

```text
GET /research/runs/{run_id}/evidence
```

Что показать:

- `source_id`;
- `chunk_id`;
- `source_type`;
- `research_block`;
- `relevance_score`;
- `trust_score`.

Что сказать:

> Evidence хранится отдельно от текста отчета. Любой вывод можно проверить через исходный фрагмент.

### Шаг 6. Открыть claims

В UI:

```text
Претензии tab
```

Endpoint:

```text
GET /research/runs/{run_id}/claims
```

Что показать:

- `claim_id`;
- `claim_text`;
- `evidence_ids`;
- `source_ids`;
- `confidence`.

Что сказать:

> Это ключевое отличие от чат-бота: отчет можно разложить на проверяемые утверждения.

### Шаг 7. Открыть graph links

В UI:

```text
Претензии tab -> graph summary
```

Endpoint:

```text
GET /research/runs/{run_id}/graph
```

Что показать:

- `source_count`;
- `evidence_count`;
- `claim_count`;
- `edge_count`;
- связи `claim -> evidence -> source`.

Что сказать:

> Мы применяем lightweight-вариант research wiki: raw sources остаются source of truth, а связи между источниками, evidence и claims становятся отдельным JSON-артефактом для интеграции.

### Шаг 8. Upload knowledge-base document

В UI:

```text
+ -> Загрузить документы -> выбрать .md/.txt/.pdf/.html -> Запустить
```

Endpoint:

```text
POST /research/run-with-files
```

Пример:

```bash
curl -X POST http://127.0.0.1:8000/research/run-with-files \
  -F "topic=AI fraud detection in insurance" \
  -F "actor_id=demo_analyst" \
  -F "actor_role=analyst" \
  -F "auto_discover_sources=false" \
  -F "files=@./research_note.md;type=text/markdown"
```

Что сказать:

> Это важно для open-source и банковской интеграции: тот же движок может работать не только по public discovery, но и по локальным справочникам, регламентам или загруженным материалам без отправки документов наружу.

### Шаг 9. Reviewer workflow

В UI:

```text
Review tab -> Mark reviewed -> Approve
```

Endpoint:

```text
POST /research/runs/{run_id}/review
```

Первый body:

```json
{
  "actor_id": "demo_reviewer",
  "actor_role": "reviewer",
  "decision": "reviewed",
  "notes": "Evidence table and claim traceability checked."
}
```

Второй body:

```json
{
  "actor_id": "demo_reviewer",
  "actor_role": "reviewer",
  "decision": "approved",
  "notes": "Approved for demo."
}
```

Что сказать:

> Аналитик не является единственной точкой контроля. Отчет проходит human-in-the-loop review.

### Шаг 10. Sensitive request check

В UI:

```text
Topic = CLTV for ivan@example.com -> Run pipeline
```

Endpoint:

```text
POST /research/run
```

Body:

```json
{
  "topic": "CLTV for ivan@example.com",
  "use_live_fetch": false,
  "actor_id": "demo_analyst",
  "actor_role": "analyst"
}
```

Что показать:

- `status = blocked`;
- `sensitivity = block`;
- `quality_gate = fail`;
- отсутствует report review.

Что сказать:

> Запрос с персональными данными блокируется до LLM-синтеза.

## Fallback Plan

Если local Qwen не отвечает:

1. Переключиться на offline mode.
2. Показать `model_gateway.synthesis_status=fallback`.
3. Объяснить, что fallback является feature, а не багом: демо воспроизводимо без внешних API и без LLM.

Команды:

```bash
export LLM_GATEWAY_MODE=offline_template
export LLM_PROVIDER=offline
export LLM_MODEL=template-report-v1
export LLM_EXTERNAL_CALLS_ENABLED=false
```

## Финальная фраза

> Мы построили безопасный исследовательский ассистент для банковских команд. Он автоматизирует первичный сбор и структурирование открытой информации, сохраняет банковские данные внутри закрытого контура, работает через локальную или корпоративную LLM-платформу и выдает проверяемый отчет с источниками, confidence и списком неопределенностей.
