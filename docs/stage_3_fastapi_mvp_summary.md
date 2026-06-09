# Stage 3 Summary: FastAPI MVP

## Статус

Stage 3 закрыт: добавлен FastAPI service layer поверх модульного `run_research_pipeline()` и file-based хранилище запусков.

## Цель

Сделать инструмент легко интегрируемым:

- core pipeline остается Python-библиотекой;
- CLI остается простым способом локального запуска;
- FastAPI дает HTTP-интерфейс и OpenAPI schema;
- будущий frontend или банковский портал сможет вызывать API без знания внутренней реализации pipeline.

## Добавленные endpoints

- `GET /health`
- `POST /research/run`
- `GET /research/runs`
- `GET /research/runs/{run_id}/status`
- `GET /research/runs/{run_id}/report`
- `GET /research/runs/{run_id}/evidence`
- `GET /research/report` - quick demo endpoint для последнего отчета
- `GET /research/evidence` - quick demo endpoint для последней evidence CSV

## Run storage

Каждый API-запуск получает `run_id` формата:

```text
run_YYYYMMDDTHHMMSSZ_xxxxxxxx
```

Артефакты сохраняются в:

```text
reports/api_runs/{run_id}/
```

Внутри run folder:

- `metadata.json` - topic, status, sensitivity, quality gate, metrics и список artifacts;
- `report.md` - Markdown-отчет;
- `evidence.csv` - evidence table для ручной проверки;
- `evidence.jsonl` - structured evidence для frontend/API-интеграций;
- `evaluation.json` - метрики pipeline.

## Запуск

```bash
PYTHONPATH=.:src uvicorn api.main:app --reload
```

Swagger UI:

```text
http://127.0.0.1:8000/docs
```

## Проверки

- `tests/test_api.py`
- FastAPI `TestClient`
- full pytest suite through `.venv`

Последний прогон:

- API tests: 6 passed
- Full tests: 19 passed
- `compileall`: passed

## Текущие ограничения

- API пока синхронный;
- хранилище запусков file-based, без БД;
- нет auth/roles/audit;
- live-fetch лучше использовать осторожно, потому что публичные сайты могут timeout/SSL/403.

## Следующий шаг

Перейти к Stage 4:

1. добавить audit log;
2. расширить policy checks;
3. добавить source allowlist;
4. описать role model;
5. усилить traceability между тезисами отчета и evidence;
6. подготовить bank-ready demo сценарий.
