# Final Presentation Outline

## Формат

Рекомендуемая длина: 8-10 слайдов.

Длительность: 5-7 минут demo + 3-5 минут вопросы.

## Slide 1. Название

Название:

```text
Bank Research Assistant
```

Subtitle:

```text
Evidence-first аналитический ассистент для банковских команд
```

Ключевая фраза:

> Мы автоматизируем первичный research по открытым источникам, но сохраняем проверяемость, контроль источников и заменяемость LLM.

## Slide 2. Проблема

Банковские аналитики тратят время на:

- поиск источников;
- чтение отчетов и PDF;
- фильтрацию шума;
- проверку фактов;
- подготовку первичной записки.

Обычный LLM-chat не подходит:

- может галлюцинировать;
- не всегда показывает sources;
- риск отправки внутренних данных наружу;
- нет audit trail;
- нет human review.

## Slide 3. Наше решение

Pipeline:

```text
Topic -> Plan -> Sources -> Clean -> Filter -> Evidence -> Claims -> Report -> Review
```

Ключевой результат:

- отчет;
- evidence table;
- claim/evidence traceability;
- quality gate;
- audit log.

## Slide 4. Архитектура

Показать Mermaid-схему из:

```text
docs/architecture.md
```

Акценты:

- Sensitivity Classifier;
- Source Policy;
- Evidence Store;
- LLM Gateway;
- Quality Gate;
- Reviewer Workflow;
- Audit Log.

## Slide 5. Почему это bank-ready

Пункты:

- default mode не делает внешних LLM-вызовов;
- local Qwen работает на ноутбуке;
- AlfaGen/GigaChat подключаются через gateway;
- источники контролируются allowlist;
- reviewer утверждает отчет;
- audit фиксирует действия.

## Slide 6. Live Demo

Показать:

1. `GET /admin/source-policy`.
2. `POST /research/run`.
3. `GET /research/runs/{run_id}/report`.
4. `GET /research/runs/{run_id}/claims`.
5. `POST /research/runs/{run_id}/review`.

Demo script:

```text
docs/final_demo_script.md
```

## Slide 7. Качество

Метрики:

- Source Precision@K;
- Citation Accuracy;
- Hallucination Risk;
- Noise Reduction;
- Evidence Coverage;
- Time to Brief;
- Human Acceptance Rate.

Файл:

```text
docs/evaluation_metrics.md
```

## Slide 8. Open-source интегрируемость

Показать:

- FastAPI endpoints;
- `.env.example`;
- local/corporate LLM profiles;
- modular `src/research_assistant`;
- tests.

Ключевая фраза:

> UI можно заменить, модель можно заменить, источники можно настроить, но core research contract остается тем же.

## Slide 9. Ограничения

Честно сказать:

- MVP использует curated seed sources;
- live search пока не production connector;
- fact checking пока базовый;
- роли не заменяют production IAM;
- audit пока JSONL, не enterprise audit store.

Почему это нормально:

> MVP доказывает архитектуру и end-to-end value, а не притворяется готовой банковской платформой.

## Slide 10. Roadmap

Показать:

- demo UI;
- source connectors;
- PDF parsing;
- embeddings reranker;
- stronger critic;
- enterprise IAM/secrets/audit;
- AlfaGen/GigaChat production adapters.

Финальная фраза:

> Мы построили фундамент безопасного research assistant: evidence-first, auditable, model-agnostic и готовый к интеграции в банковский контур.

