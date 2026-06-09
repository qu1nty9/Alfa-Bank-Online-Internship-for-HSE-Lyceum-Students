# Alfa-Bank Online Internship for HSE Lyceum Students

Прототип банковского research assistant для автоматизированной аналитики по открытым источникам.

Базовый демо-сценарий: исследование темы "Применение CLTV в иностранных банках".

## Цель проекта

Собрать работающий прототип, который помогает банковскому аналитику быстро разобраться в новой теме:

1. принять тему исследования;
2. построить план исследования;
3. собрать открытые источники или использовать подготовленный seed-набор;
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

Ключевой результат Stage 2: `research_assistant.pipeline.run_research_pipeline()`.

Ключевой результат Stage 3: API-запуски с `run_id`, хранилищем metadata и endpoints для получения статуса, отчета и evidence по конкретному запуску.

## Структура проекта

```text
.
├── data/
│   ├── clean/              # очищенные тексты
│   ├── raw/                # сырые скачанные HTML/PDF/тексты
│   └── seed_sources/       # подготовленные источники и шаблоны
├── docs/                   # постановка, планы, материалы защиты
├── notebooks/              # эксперименты и Notebook MVP
├── reports/                # сгенерированные аналитические отчеты
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

Запустить модульный pipeline без live-fetch, по cached clean documents:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks"
```

Получить JSON-summary:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --json
```

Запустить pipeline с live-fetch:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --live-fetch --fetch-limit 8
```

Запустить FastAPI MVP:

```bash
PYTHONPATH=.:src uvicorn api.main:app --reload
```

API endpoints:

- `GET /health`
- `POST /research/run`
- `GET /research/runs`
- `GET /research/runs/{run_id}/status`
- `GET /research/runs/{run_id}/report`
- `GET /research/runs/{run_id}/evidence`
- `GET /research/report` - quick demo endpoint для последнего отчета
- `GET /research/evidence` - quick demo endpoint для последней evidence CSV
- Swagger UI: `http://127.0.0.1:8000/docs`

Пример API-запуска:

```bash
curl -X POST http://127.0.0.1:8000/research/run \
  -H "Content-Type: application/json" \
  -d '{"topic":"CLTV in foreign banks","use_live_fetch":false}'
```

## Основные документы

- `docs/project_work_plan.md` - подробный план проекта до финального результата.
- `docs/demo_scenario_cltv.md` - сценарий демонстрации по теме CLTV.
- `docs/stage_1_notebook_mvp_summary.md` - закрытие Notebook MVP.
- `docs/stage_2_modular_pipeline_summary.md` - модульный Python-конвейер.
- `docs/stage_3_fastapi_mvp_summary.md` - закрытие FastAPI MVP.
- `docs/stage_3_swagger_demo.md` - сценарий демонстрации через Swagger UI.
- `api/README.md` - FastAPI MVP.
- `data/seed_sources/cltv_sources_template.csv` - шаблон для списка источников.

## Модульный pipeline

Основные модули:

- `config.py` - настройки путей и параметров pipeline;
- `sensitivity.py` - проверка чувствительных запросов;
- `planner.py` - research plan;
- `collector.py` - seed-source collector;
- `fetcher.py` - raw fetching;
- `parser.py` - clean text extraction;
- `chunker.py` - chunking;
- `filtering.py` - noise filter и BM25 ranking;
- `evidence.py` - evidence table;
- `report.py` - template-based report;
- `quality_gate.py` - проверки результата;
- `pipeline.py` - orchestration.

## Ближайший практический шаг

Перейти к Stage 4: добавить bank-ready слой - audit log, расширенные policy checks, source allowlist, role model и более строгую traceability между тезисами отчета и evidence.
