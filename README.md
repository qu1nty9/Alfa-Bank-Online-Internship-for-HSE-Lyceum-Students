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

Этап 2 реализован: логика notebook вынесена в модульный Python-конвейер, который можно запускать через CLI и позже подключить к Streamlit/FastAPI UI.

Ключевой результат Stage 2: `research_assistant.pipeline.run_research_pipeline()`.

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

## Основные документы

- `docs/project_work_plan.md` - подробный план проекта до финального результата.
- `docs/demo_scenario_cltv.md` - сценарий демонстрации по теме CLTV.
- `docs/stage_1_notebook_mvp_summary.md` - закрытие Notebook MVP.
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

Этап 3: Web/UI MVP. Быстрый путь для демонстрации - Streamlit-интерфейс поверх `run_research_pipeline()`.
