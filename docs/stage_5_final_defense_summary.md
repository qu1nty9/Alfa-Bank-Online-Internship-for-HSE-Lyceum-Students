# Stage 5 Start: Final Defense Package

## Цель

Stage 5 превращает рабочий прототип в понятный демонстрационный продукт для защиты.

Фокус этапа:

- показать end-to-end сценарий, а не отдельные модули;
- объяснить, почему это bank-ready research assistant, а не обычный LLM-chat;
- заранее подготовить ответы на вопросы про качество, безопасность, источники и заменяемость LLM;
- сделать финальный pitch воспроизводимым на любом ноутбуке.

## Что уже готово к Stage 5

Проект уже имеет:

1. Notebook MVP.
2. Модульный Python pipeline.
3. FastAPI MVP.
4. Source policy / allowlist.
5. Audit log.
6. Role model: `analyst`, `reviewer`, `admin`.
7. Claim/evidence traceability.
8. LLM Gateway с профилями:
   - offline template;
   - local Qwen через Ollama;
   - AlfaGen через OpenAI-compatible endpoint;
   - GigaChat profile.
9. Local Qwen3-1.7B установлен и проверен на машине участника.

## Stage 5 deliverables

### 1. Final demo script

Файл:

```text
docs/final_demo_script.md
```

Задача: дать команде сценарий показа на 5-7 минут с командами, expected outputs и fallback-планом.

### 2. Evaluation metrics

Файл:

```text
docs/evaluation_metrics.md
```

Задача: показать, как оценивается качество источников, evidence, claims, hallucination risk и time-to-brief.

### 3. Roadmap

Файл:

```text
docs/roadmap.md
```

Задача: отделить MVP от production-ready версии и показать зрелость дальнейшего развития.

### 4. Presentation outline

Файл:

```text
docs/final_presentation_outline.md
```

Задача: подготовить структуру финального pitch deck на 8-10 слайдов.

## Рекомендуемый следующий шаг

Сделать минимальный UI поверх FastAPI:

- поле ввода темы;
- кнопка запуска;
- tabs: `Report`, `Evidence`, `Claims`, `Review`, `Audit`;
- badge текущей модели: `offline_template` / `local_qwen`;
- кнопки reviewer workflow.

Это улучшит визуальную сторону защиты, но не является блокером: Swagger UI уже достаточно для инженерного демо.

