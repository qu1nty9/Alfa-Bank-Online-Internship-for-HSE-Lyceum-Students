# Alfa-Bank Online Internship for HSE Lyceum Students

Прототип open-source research assistant для автоматизированной аналитики по открытым источникам.

Один из демо-сценариев: исследование темы "Применение CLTV в иностранных банках".

Core pipeline не ограничен CLTV: для любой темы он строит generic research plan, расширяет запросы, автоматически ищет публичные источники через discovery connectors, принимает вручную переданные source URLs и умеет анализировать загруженные `.md`, `.txt`, `.pdf`, `.html` документы. CLTV больше не является особым runtime-режимом: это только пример темы и demo fixture.

## Цель проекта

Собрать работающий прототип, который помогает банковскому аналитику быстро разобраться в новой теме:

1. принять тему исследования;
2. построить план исследования;
3. собрать открытые источники через единый discovery layer;
4. очистить и отфильтровать информационный шум;
5. сохранить проверяемые evidence-фрагменты;
6. сформировать аналитическую записку с источниками;
7. проверить, что ключевые выводы подтверждены evidence.

## Почему это не обычный чат-бот

Банковский сценарий требует контролируемого контура:

- внутренние данные банка не отправляются во внешние LLM/API;
- наружу могут уходить только обезличенные поисковые запросы по публичной теме;
- каждый важный вывод должен иметь источник;
- LLM подключается через заменяемый gateway;
- аналитик утверждает итоговый отчет;
- сбор источников должен быть легитимным: API, RSS, официальные документы, отчеты и разрешенный web-доступ.

## Текущий статус

Этап 1 закрыт: есть воспроизводимый Notebook MVP.

Этап 2 реализован: логика notebook вынесена в модульный Python-конвейер, который можно запускать через CLI.

Этап 3 закрыт: добавлен FastAPI MVP поверх `run_research_pipeline()` для интеграции с внешними сервисами и будущим frontend.

Этап 4 закрыт: добавлены audit log, actor metadata, role enforcement, report review workflow, claim/evidence traceability, source allowlist config, admin workflow и формальный LLM Gateway contract.

Этап 5 в работе: добавлены материалы финальной защиты, demo script, метрики качества, roadmap, структура презентации и единое demo UI с topic input, upload-файлами, историей запусков и claim/evidence/source graph.

Ключевой результат Stage 2: `research_assistant.pipeline.run_research_pipeline()`.

Ключевой результат Stage 3: API-запуски с `run_id`, хранилищем metadata и endpoints для получения статуса, отчета и evidence по конкретному запуску.

Ключевой результат Stage 4: каждый API-запуск оставляет audit trail, отчет проходит reviewer workflow, ключевые claims связаны с evidence, source allowlist управляется через admin API, а LLM Gateway заменяем между offline, local Qwen, AlfaGen/GigaChat и OpenAI-compatible endpoints.

Ключевой результат текущего Stage 5: продуктовый no-build UI поверх FastAPI, multipart upload endpoint, поддержка uploaded knowledge-base documents и lightweight graph layer `claim -> evidence -> source`.

## Структура проекта

```text
.
├── data/
│   ├── clean/              # очищенные тексты
│   ├── raw/                # сырые скачанные HTML/PDF/тексты
│   └── seed_sources/       # подготовленные источники и шаблоны
├── config/                 # policy configs для банковского контура
├── docs/                   # постановка, планы, материалы защиты
├── notebooks/              # эксперименты и Notebook MVP
├── reports/                # сгенерированные аналитические отчеты
├── api/static/             # lightweight no-build demo UI
├── src/
│   └── research_assistant/ # код прототипа
└── tests/                  # проверки модулей
```

## Быстрый старт

Создать окружение:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Проверить каркас:

```bash
pytest
```

Открыть стартовый notebook:

```bash
jupyter notebook notebooks/00_cltv_research_mvp.ipynb
```

Запустить модульный pipeline через единый auto-discovery режим:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks"
```

Явный offline demo по подготовленному seed-набору:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --source-strategy seed_sources
```

Получить JSON-summary:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --json
```

Запустить pipeline с live-fetch:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --live-fetch --fetch-limit 8
```

Для любой темы через API/UI можно просто ввести topic: auto discovery включен по умолчанию. Публичные source URLs можно добавить вручную, если нужно усилить или зафиксировать набор источников. В UI также можно загрузить `.md`, `.txt`, `.pdf`, `.html` файлы: они будут распарсены локально и пройдут через тот же noise filtering, evidence extraction, report, review и audit контур.

Запустить FastAPI MVP:

```bash
PYTHONPATH=.:src uvicorn api.main:app --reload
```

Открыть demo UI:

```text
http://127.0.0.1:8000/ui
```

API endpoints:

- `GET /` / `GET /ui` - lightweight demo UI
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
- `GET /admin/source-policy`
- `PUT /admin/source-policy`
- `GET /admin/audit-events`
- `GET /research/report` - quick demo endpoint для последнего отчета
- `GET /research/evidence` - quick demo endpoint для последней evidence CSV
- Swagger UI: `http://127.0.0.1:8000/docs`

Пример API-запуска:

```bash
curl -X POST http://127.0.0.1:8000/research/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"CLTV in foreign banks","use_live_fetch":false,"actor_id":"demo_analyst","actor_role":"analyst"}'
```

Пример любой темы с automatic source discovery:

```bash
curl -X POST http://127.0.0.1:8000/research/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"AI fraud detection in insurance","actor_id":"demo_analyst","actor_role":"analyst","auto_discover_sources":true}'
```

Пример любой темы с пользовательскими источниками:

```bash
curl -X POST http://127.0.0.1:8000/research/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"AI fraud detection in insurance","actor_id":"demo_analyst","actor_role":"analyst","auto_discover_sources":false,"source_urls":["https://example.com/public-report"]}'
```

Пример любой темы с локальным markdown-документом:

```bash
curl -X POST http://127.0.0.1:8000/research/run-with-files \
  -F "topic=AI fraud detection in insurance" \
  -F "actor_id=demo_analyst" \
  -F "actor_role=analyst" \
  -F "auto_discover_sources=false" \
  -F "files=@./research_note.md;type=text/markdown"
```

Локальная LLM для демо:

```text
docs/local_llm.md
```

## Основные документы

- `docs/project_work_plan.md` - подробный план проекта до финального результата.
- `docs/architecture.md` - bank-ready архитектура и поток данных.
- `docs/demo_scenario_cltv.md` - сценарий демонстрации по теме CLTV.
- `docs/final_demo_script.md` - пошаговый сценарий финального демо.
- `docs/evaluation_metrics.md` - метрики качества и как их показывать.
- `docs/roadmap.md` - путь от MVP к production-ready решению.
- `docs/final_presentation_outline.md` - структура финальной презентации.
- `docs/stage_1_notebook_mvp_summary.md` - закрытие Notebook MVP.
- `docs/stage_2_modular_pipeline_summary.md` - модульный Python-конвейер.
- `docs/stage_3_fastapi_mvp_summary.md` - закрытие FastAPI MVP.
- `docs/stage_3_swagger_demo.md` - сценарий демонстрации через Swagger UI.
- `docs/stage_4_bank_ready_start_summary.md` - закрытие Stage 4: audit/roles/review/source allowlist/model gateway metadata.
- `docs/stage_5_final_defense_summary.md` - старт Stage 5: final defense package.
- `docs/local_llm.md` - подключение Qwen3-1.7B, AlfaGen/GigaChat и OpenAI-compatible endpoints.
- `api/README.md` - FastAPI MVP.
- `api/static/` - no-build demo UI поверх FastAPI.
- `config/source_policy.json` - file-backed source allowlist для admin-сценария.
- `data/seed_sources/cltv_sources_template.csv` - явный offline demo fixture, не runtime fallback.

## Модульный pipeline

Основные модули:

- `config.py` - настройки путей и параметров pipeline;
- `sensitivity.py` - проверка чувствительных запросов;
- `planner.py` - research plan;
- `collector.py` - ручные source URLs и explicit seed fixtures;
- `source_discovery.py` - public source discovery: Wikipedia, OpenAlex, arXiv, Crossref, optional SearXNG/Search endpoint;
- `fetcher.py` - raw fetching;
- `parser.py` - clean text extraction;
- `chunker.py` - chunking;
- `filtering.py` - noise filter и BM25 ranking;
- `evidence.py` - evidence table;
- `knowledge_graph.py` - lightweight claim/evidence/source graph;
- `report.py` - template-based report;
- `quality_gate.py` - проверки результата;
- `pipeline.py` - orchestration.

## Ближайший практический шаг

Продолжить Stage 5: собрать финальную презентацию на основе `docs/final_presentation_outline.md` и прогнать demo script через `/ui`.
