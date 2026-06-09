# Stage 1 Summary: Notebook MVP

## Статус

Этап 1 закрыт как воспроизводимый Notebook MVP.

Notebook `notebooks/00_cltv_research_mvp.ipynb` проходит путь от темы исследования до первого evidence-first Markdown-отчета и quality gate.

## Что реализовано

1. Research Planner
   - rule-based план исследования по теме CLTV;
   - блоки: business value, calculation methods, required data, banking use cases, risks.

2. Seed Source Collector
   - curated CSV с 12 публичными источниками;
   - валидация URL и metadata;
   - группировка по research blocks.

3. Fetching
   - загрузка raw HTML/PDF в `data/raw`;
   - кэширование raw-файлов;
   - safe batch режим: ошибки отдельных сайтов не ломают весь запуск.

4. Parsing
   - HTML parsing через стандартную библиотеку;
   - PDF parsing через `pypdf`, если доступен;
   - clean text сохраняется в `data/clean`.

5. Chunking
   - разбиение clean text на стабильные фрагменты;
   - сохранение `source_id`, `chunk_id`, source metadata и позиции.

6. Baseline Filtering
   - удаление коротких фрагментов;
   - удаление consent/cookie/country-selector шума;
   - доменная фильтрация по banking/CLTV terms;
   - дедупликация.

7. BM25 Ranking
   - собственная baseline-реализация BM25 без внешних зависимостей;
   - ranking chunks по queries из Research Planner.

8. Evidence Table
   - построение evidence items;
   - балансировка покрытия по research blocks;
   - экспорт CSV/JSONL.

9. Template Report
   - первый Markdown-отчет без LLM;
   - отчет строится только по evidence;
   - содержит evidence table и unknowns.

10. Quality Gate
    - проверка количества clean documents;
    - проверка количества evidence items;
    - проверка diversity источников;
    - проверка coverage ключевых blocks;
    - проверка наличия evidence table и unknowns.

## Последний проверенный прогон

- Seed sources: 12
- Clean documents: 8
- Chunks: 199
- Filtered chunks: 177
- Noise reduction: 11.1%
- Evidence items: 11
- Evidence source count: 5
- Required evidence blocks: covered
- Quality gate: pass

## Источники, которые не загрузились автоматически

- `seed_004` McKinsey: timeout
- `seed_005` McKinsey: timeout
- `seed_010` Experian PDF: SSL certificate verification issue
- `seed_011` Capco: timeout

Эти ограничения не блокируют Этап 1, потому что pipeline уже работает на 8 clean-документах и покрывает обязательные research blocks. Для Этапа 2 стоит добавить более зрелый fetching layer: `httpx`, retries, PDF-specific downloader, optional Playwright fallback и ручной allowlist.

## Generated outputs

Следующие файлы генерируются локально и не коммитятся:

- `data/raw/*`
- `data/clean/*`
- `reports/evidence_cltv.csv`
- `reports/evidence_cltv.jsonl`
- `reports/evaluation_cltv.json`
- `reports/report_cltv.md`

## Definition of Done

Этап 1 считается закрытым, потому что notebook:

1. запускается сверху вниз;
2. строит research plan;
3. загружает curated seed sources;
4. использует cached clean documents;
5. делает chunking;
6. фильтрует шум;
7. ранжирует chunks через BM25;
8. строит evidence table;
9. генерирует первый Markdown-отчет;
10. запускает quality gate со статусом `pass`;
11. явно фиксирует ограничения MVP.

