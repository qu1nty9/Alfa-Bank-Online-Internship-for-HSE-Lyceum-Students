# Stage 2 Summary: Modular Python Pipeline

## Статус

Этап 2 реализован как модульный Python-конвейер с CLI-запуском и offline integration test.

## Цель

Перенести orchestration из notebook в переиспользуемый Python-конвейер.

Notebook остается демонстрационной оболочкой, но основной запуск теперь должен быть возможен через Python API и CLI.

## Что добавлено

1. `config.py`
   - единая конфигурация путей;
   - параметры fetching, chunking, filtering, BM25 и quality gate.

2. `sensitivity.py`
   - rule-based проверка чувствительных запросов;
   - решения: `allow`, `warn`, `block`;
   - блокировка email/phone/long number паттернов.

3. `llm_gateway.py`
   - mock/stub интерфейс для будущей модели;
   - пока не вызывает внешние LLM.

4. `pipeline.py`
   - функция `run_research_pipeline()`;
   - CLI entrypoint через `python -m research_assistant.pipeline`;
   - offline/cached режим по умолчанию;
   - optional live-fetch через флаг `--live-fetch`.

5. Integration test
   - создает временный проект;
   - использует локальные clean fixtures;
   - запускает pipeline без сети;
   - проверяет report и quality gate.

## Почему это важно

- notebook больше не является единственным orchestrator;
- будущий Streamlit/FastAPI UI сможет вызывать один и тот же pipeline;
- компоненты остаются тестируемыми отдельно;
- можно заменить seed collector на Search API без переписывания отчета и quality gate;
- можно заменить template report на LLM synthesizer через `llm_gateway.py`.

## CLI

Offline/cached запуск:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks"
```

JSON-summary:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --json
```

Live-fetch запуск:

```bash
PYTHONPATH=src python -m research_assistant.pipeline --topic "CLTV in foreign banks" --live-fetch --fetch-limit 8
```

## Definition of Done для полного закрытия Stage 2

Stage 2 можно считать закрытым, потому что:

1. pipeline запускается через CLI;
2. pipeline проходит integration test без сети;
3. sensitivity check блокирует чувствительные запросы;
4. generated report/evidence/evaluation создаются через pipeline;
5. README описывает CLI-команды;
6. notebook может остаться как walkthrough, но orchestration уже доступен из `pipeline.py`.

## Последний проверенный прогон

- CLI offline/cached run: `quality_gate = pass`
- Clean documents: 8
- Chunks: 199
- Filtered chunks: 177
- Evidence items: 15
- Evidence source count: 5
- Sensitivity blocked-query smoke: sensitive email query returns `block`
- Manual tests: passed
- `compileall`: passed

`pytest` не запускался в текущем системном Python, потому что пакет `pytest` не установлен. После установки `requirements.txt` команда `pytest` должна использовать те же тестовые функции.
