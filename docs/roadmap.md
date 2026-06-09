# Roadmap

## Цель

Roadmap отделяет текущий MVP от production-ready банковского решения.

## Сейчас реализовано

### MVP

- Notebook MVP.
- Модульный Python pipeline.
- FastAPI service layer.
- Seed-source collector.
- Parser/cleaner.
- Noise filter и BM25 reranker.
- Evidence store.
- Template report.
- Claim/evidence traceability.
- Quality gate.
- Audit log.
- Reviewer workflow.
- Source allowlist.
- LLM Gateway.
- Local Qwen profile.
- AlfaGen/GigaChat-ready gateway profiles.

## Ближайшие улучшения

### 1. Demo UI

Сделать легкий UI поверх FastAPI:

- input темы;
- переключатель LLM mode;
- таблица runs;
- tabs: report/evidence/claims/review/audit;
- кнопки reviewer workflow;
- export report.

Рекомендуемый путь:

```text
FastAPI static HTML + JavaScript
```

Почему:

- меньше инфраструктуры;
- легче запускать open-source пользователю;
- API остается главным integration contract.

### 2. Source connectors

Добавить легитимные источники:

- RSS;
- official APIs;
- вручную одобренные public PDFs;
- search API через обезличенные публичные queries.

Не делать ценностью проекта:

- обход anti-bot;
- парсинг закрытых источников;
- отправку внутренних данных наружу.

### 3. Better parsing

Улучшить extraction:

- PDF parser;
- HTML boilerplate removal;
- language detection;
- document deduplication;
- source freshness metadata.

### 4. Better reranking

Добавить:

- embeddings reranker;
- domain classifier;
- source trust calibration;
- block-level coverage scoring.

### 5. Stronger fact checking

Добавить critic layer:

- claim extraction from final report;
- automatic source support check;
- numeric claim validation;
- contradiction detection;
- unsupported claim warnings.

### 6. Enterprise security

Production banking layer:

- SSO/IAM;
- secrets management;
- VPC/on-prem deployment;
- structured audit store;
- retention policy;
- PII detection model;
- policy engine integration.

### 7. Corporate LLM integration

Интеграции:

- AlfaGen adapter;
- GigaChat OAuth/token flow;
- internal OpenAI-compatible gateway;
- model registry;
- prompt/version logging.

## Production Architecture Target

```mermaid
flowchart LR
    ui["Bank UI"] --> api["Research API"]
    api --> iam["IAM / SSO"]
    api --> policy["Policy Engine"]
    policy --> collector["Approved Connectors"]
    collector --> store["Evidence Store"]
    store --> gateway["Corporate LLM Gateway"]
    gateway --> model["Approved LLM"]
    store --> quality["Quality Gate + Critic"]
    quality --> review["Human Review"]
    review --> audit["Audit Store"]
```

## Что не является целью MVP

- заменять аналитика;
- принимать бизнес-решения автоматически;
- работать с персональными клиентскими данными;
- обходить ограничения сайтов;
- доказывать production-grade безопасность.

MVP показывает архитектурную зрелость и рабочий прототип, который можно развивать в банковском контуре.

