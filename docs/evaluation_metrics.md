# Evaluation Metrics

## Цель

Метрики нужны, чтобы показать качество research assistant не на уровне "текст выглядит хорошо", а через проверяемые свойства pipeline.

## Метрики для MVP

### 1. Source Precision@K

Что измеряет:

- сколько источников в top evidence действительно релевантны теме банковского CLTV.

Как считать:

```text
relevant_sources_in_top_k / k
```

Текущий MVP:

- proxy: ручная проверка `evidence.jsonl`;
- источники ограничены `config/source_policy.json`;
- source types: `consulting`, `academic`, `vendor`, `official_bank`, `regulator`.

Целевой уровень для демо:

```text
Precision@10 >= 0.8
```

### 2. Citation Accuracy

Что измеряет:

- долю claims, которые действительно поддержаны evidence ids.

Как считать:

```text
supported_claims / all_claims
```

Где смотреть:

```text
GET /research/runs/{run_id}/claims
GET /research/runs/{run_id}/evidence
```

Целевой уровень для демо:

```text
Citation accuracy >= 0.8
```

### 3. Hallucination Risk

Что измеряет:

- долю утверждений без evidence;
- наличие неподтвержденных чисел;
- наличие выводов, которых нет в источниках.

Как считать для MVP:

```text
unsupported_claims / all_claims
```

Практическая проверка:

- claims без `evidence_ids` должны отсутствовать или иметь статус `needs_review`;
- любые точные проценты/суммы должны иметь evidence;
- если модель недоступна, pipeline должен уйти в template fallback.

Целевой уровень для демо:

```text
Unsupported claims <= 0.2
```

### 4. Noise Reduction

Что измеряет:

- насколько pipeline уменьшает объем текста до полезного evidence.

Как считать:

```text
1 - filtered_chunk_count / raw_chunk_count
```

Где смотреть:

```text
evaluation_summary
```

Целевой уровень для демо:

```text
Noise reduction: объяснимый warn/pass, без удаления всех источников
```

### 5. Evidence Coverage

Что измеряет:

- сколько research blocks получили evidence.

Как считать:

```text
blocks_with_evidence / all_research_blocks
```

Целевой уровень для демо:

```text
Coverage >= 0.7
```

### 6. Time to Brief

Что измеряет:

- сколько времени занимает путь от темы до первичного отчета.

Как считать:

```text
completed_at - created_at
```

Где смотреть:

```text
GET /research/runs/{run_id}/status
```

Целевой уровень для демо:

```text
Offline/cached run: under 10 seconds
Local LLM run: depends on laptop, but should stay demo-friendly
```

### 7. Human Acceptance Rate

Что измеряет:

- сколько отчетов reviewer переводит в `approved`.

Как считать:

```text
approved_reports / reviewed_reports
```

Где смотреть:

```text
review.history
reports/audit/research_runs.jsonl
```

Для MVP:

- показываем один ручной сценарий `draft -> reviewed -> approved`;
- в production это станет регулярной quality metric.

## Quality Gate Mapping

Текущий `quality_gate` должен отвечать на вопрос: можно ли показать отчет аналитику.

`pass`:

- достаточно clean documents;
- достаточно evidence items;
- достаточно разных sources;
- нет sensitive block.

`warn`:

- отчет создан, но coverage или evidence могут быть слабее целевого уровня;
- нужен reviewer check.

`fail`:

- sensitive query;
- недостаточно evidence;
- отчет не должен идти в business usage.

## Как показать метрики на защите

1. Открыть response `POST /research/run`.
2. Показать `evaluation_summary`.
3. Показать `quality_gate`.
4. Открыть `claims`.
5. Открыть `evidence`.
6. Объяснить, что production-версия добавит автоматизированную разметку relevance и регулярный benchmark set.

