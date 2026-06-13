# Seed cache: frozen clean texts for the offline CLTV demo

Committed snapshot of clean text extracted from the REAL public seed sources
listed in `data/seed_sources/cltv_sources_template.csv`.

- Fetched live on 2026-06-10 via `research_assistant.fetcher` (one-time run with
  `use_live_fetch=True`), parsed by the project's own parser, content unmodified.
- Filenames are the seed `source_id`s; url/title metadata for each file comes from
  the seed CSV row with the same id.
- The pipeline reads these only as a fallback: fresh files in `data/clean/` always
  take precedence (see `pipeline._load_cached_clean_documents`).
- Sources seed_004, seed_005, seed_010, seed_011 are absent: their sites refused
  the fetch (timeouts / HTTP 403) at snapshot time.

| file | url | title |
| --- | --- | --- |
| seed_001.txt | https://www.teradata.com/insights/brochures/customer-lifetime-value-in-banking | Customer Lifetime Value in Banking |
| seed_002.txt | https://www.teradata.com/insights/ai-and-machine-learning/application-of-customer-lifetime-value-models | Application of Customer Lifetime Value Models in Banking |
| seed_003.txt | https://www.bcg.com/publications/2019/what-does-personalization-banking-really-mean | What Does Personalization in Banking Really Mean? |
| seed_006.txt | https://www.deloitte.com/us/en/insights/industry/financial-services/explainable-ai-in-banking.html | Explainable artificial intelligence in banking |
| seed_007.txt | https://www.bain.com/publications/articles/customer-loyalty-in-retail-banking-2012.aspx | Customer Loyalty in Retail Banking: Global Edition |
| seed_008.txt | https://arxiv.org/abs/2506.22711 | Potential Customer Lifetime Value in Financial Institutions: The Usage Of Open Banking Data to Improve CLV Estimation |
| seed_009.txt | https://arxiv.org/abs/2304.03038 | Modelling customer lifetime-value in the retail banking industry |
| seed_012.txt | https://www.bcg.com/publications/2022/customer-value-and-banking-in-the-digital-age | Customer Value and Banking in the Digital Age |
