# Stage 3 Swagger Demo

Цель: показать FastAPI MVP как легко интегрируемую оболочку над модульным research pipeline.

## 1. Запуск сервера

```bash
PYTHONPATH=.:src uvicorn api.main:app --reload
```

Открыть Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## 2. Health check

Endpoint:

```text
GET /health
```

Ожидаемый результат:

```json
{
  "status": "ok",
  "service": "bank-research-assistant"
}
```

## 3. Запуск исследования

Endpoint:

```text
POST /research/run
```

Body:

```json
{
  "topic": "CLTV in foreign banks",
  "use_live_fetch": false
}
```

Что показать:

- API возвращает `run_id`;
- `sensitivity` должен быть `allow`;
- `quality_gate` должен быть `pass` или `warn`;
- `evaluation_summary` показывает количество clean documents, chunks и evidence;
- `links` содержит paths для status, report и evidence.

## 4. Проверка статуса запуска

Endpoint:

```text
GET /research/runs/{run_id}/status
```

Что показать:

- конкретный запуск можно получить по `run_id`;
- metadata хранит topic, status, policy decision, quality gate и artifacts;
- это уже интеграционный контракт для frontend или внешней системы.

## 5. Получение отчета

Endpoint:

```text
GET /research/runs/{run_id}/report
```

Что показать:

- отчет возвращается как Markdown;
- есть executive summary;
- выводы опираются на evidence;
- отчет можно показывать во frontend или экспортировать.

## 6. Получение evidence

Endpoint:

```text
GET /research/runs/{run_id}/evidence
```

Что показать:

- evidence возвращается как JSON;
- каждый item содержит `source_id`, `chunk_id`, `text`, `url`, `matched_query` и `relevance_score`;
- frontend может строить таблицу evidence без парсинга CSV.

## 7. Проверка sensitive query

Endpoint:

```text
POST /research/run
```

Body:

```json
{
  "topic": "CLTV for ivan@example.com",
  "use_live_fetch": false
}
```

Ожидаемый результат:

- `status`: `blocked`;
- `sensitivity`: `block`;
- `quality_gate`: `fail`;
- report/evidence links отсутствуют.

## 8. Что это доказывает

- Core logic остается в `src/research_assistant`;
- API является тонким интеграционным слоем;
- каждый запуск воспроизводимо связан с `run_id`;
- отчет и evidence можно получать отдельно;
- sensitive запросы блокируются до синтеза отчета.
