from pathlib import Path

from research_assistant.chunker import chunk_clean_document
from research_assistant.collector import group_sources_by_research_block, load_seed_sources
from research_assistant.evidence import build_evidence_items, write_evidence_csv
from research_assistant.evaluation import build_evaluation_summary
from research_assistant.fetcher import fetch_sources_safe, raw_document_path
from research_assistant.filtering import filter_chunks, rank_chunks_bm25
from research_assistant.models import CleanDocument, RawDocument
from research_assistant.parser import extract_html_text, parse_raw_document, parse_raw_documents_safe
from research_assistant.planner import build_cltv_research_plan
from research_assistant.quality_gate import run_quality_gate
from research_assistant.report import render_markdown_report

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cltv_research_plan_has_required_blocks() -> None:
    plan = build_cltv_research_plan()

    assert plan.topic == "CLTV in foreign banks"
    assert "banking_use_cases" in plan.blocks
    assert len(plan.queries) >= 5


def test_seed_sources_load_real_ready_sources() -> None:
    sources = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")

    assert len(sources) >= 10
    assert all(source.status == "ready" for source in sources)
    assert {source.research_block for source in sources} >= {
        "definition_and_business_value",
        "calculation_methods",
        "banking_use_cases",
        "required_data",
        "risks_and_limitations",
    }


def test_seed_sources_can_be_grouped_by_research_block() -> None:
    sources = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")
    grouped = group_sources_by_research_block(sources)

    assert "calculation_methods" in grouped
    assert grouped["calculation_methods"][0].source_id


def test_raw_document_path_uses_source_id_and_url_extension() -> None:
    source = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")[0]

    assert raw_document_path(source, "data/raw").name == "seed_001.html"


def test_extract_html_text_removes_scripts_and_navigation() -> None:
    html = """
    <html>
      <body>
        <nav>Menu item</nav>
        <article>
          <h1>Customer Lifetime Value</h1>
          <p>Banks use CLV to prioritize retention and personalization.</p>
          <script>console.log("noise")</script>
        </article>
      </body>
    </html>
    """

    text = extract_html_text(html)

    assert "Customer Lifetime Value" in text
    assert "retention and personalization" in text
    assert "Menu item" not in text
    assert "console.log" not in text


def test_parse_raw_document_writes_clean_text(tmp_path) -> None:
    source = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")[0]
    raw_path = tmp_path / "seed_001.html"
    raw_path.write_text(
        "<main><h1>CLV</h1><p>Banking CLV depends on retention.</p></main>",
        encoding="utf-8",
    )
    raw_document = RawDocument(
        source_id=source.source_id,
        url=source.url,
        path=raw_path,
        content_type="text/html",
    )

    clean_document = parse_raw_document(raw_document, source, tmp_path / "clean")

    assert clean_document.path.exists()
    assert clean_document.parser_name == "stdlib_html_parser"
    assert "Banking CLV depends on retention." in clean_document.text


def test_safe_parse_keeps_successful_documents(tmp_path) -> None:
    source = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")[0]
    raw_path = tmp_path / "seed_001.html"
    raw_path.write_text("<main><p>Banking CLV supports retention.</p></main>", encoding="utf-8")
    raw_document = RawDocument(
        source_id=source.source_id,
        url=source.url,
        path=raw_path,
        content_type="text/html",
    )

    results = parse_raw_documents_safe([raw_document], [source], tmp_path / "clean")

    assert results[0].ok is True
    assert results[0].clean_document is not None


def test_safe_fetch_reports_failures(tmp_path) -> None:
    source = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")[0].model_copy(
        update={"url": "https://nonexistent.invalid/source"}
    )

    results = fetch_sources_safe([source], tmp_path, timeout_seconds=1)

    assert results[0].ok is False
    assert results[0].error


def test_chunk_filter_rank_and_evidence_flow(tmp_path) -> None:
    source = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")[0]
    clean_document = CleanDocument(
        source_id=source.source_id,
        title=source.title,
        url=source.url,
        path=tmp_path / "seed_001.txt",
        text=(
            "Customer lifetime value helps banks estimate customer profitability and retention.\n"
            "Banking CLV models use product holdings, channel behavior, margin, attrition, and risk.\n"
            "Noise only."
        ),
        parser_name="plain_text",
        char_count=170,
    )

    chunks = chunk_clean_document(clean_document, source, max_chars=220, overlap_chars=20, min_chars=80)
    filtered_chunks = filter_chunks(chunks, min_chars=80, min_domain_terms=2)
    ranked_chunks = rank_chunks_bm25(filtered_chunks, build_cltv_research_plan().queries, top_k_per_query=2)
    evidence_items = build_evidence_items(ranked_chunks, max_items=3)
    csv_path = write_evidence_csv(evidence_items, tmp_path / "evidence.csv")

    assert chunks
    assert filtered_chunks
    assert ranked_chunks
    assert evidence_items
    assert evidence_items[0].chunk_id.startswith(source.source_id)
    assert csv_path.exists()


def test_filter_chunks_removes_marketing_consent_noise() -> None:
    source = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")[0]
    clean_document = CleanDocument(
        source_id=source.source_id,
        title=source.title,
        url=source.url,
        path=Path("seed_001.txt"),
        text=(
            "Banking customer lifetime value helps estimate retention and profitability.\n"
            "I consent that the provider of this website may send marketing communications. "
            "Virgin Islands Select one Terms of use."
        ),
        parser_name="plain_text",
        char_count=180,
    )
    chunks = chunk_clean_document(clean_document, source, max_chars=260, overlap_chars=0, min_chars=80)

    assert filter_chunks(chunks, min_chars=80, min_domain_terms=2) == []


def test_evaluation_report_and_quality_gate_flow(tmp_path) -> None:
    plan = build_cltv_research_plan()
    sources = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")
    clean_documents = []
    fixture_texts = [
        "Customer lifetime value banking use cases help banks prioritize customer profitability and retention.",
        "Customer lifetime value calculation in banking uses retention probability, margin, products, and risk.",
        "Bank customer lifetime value data requirements include transactions, products, campaigns, and channels.",
        "CLTV next best action banking personalization retention cross sell improves customer analytics.",
        "Customer lifetime value banking privacy bias explainability risks require responsible AI controls.",
    ]
    for source, text in zip(sources[:5], fixture_texts):
        clean_documents.append(
            CleanDocument(
                source_id=source.source_id,
                title=source.title,
                url=source.url,
                path=tmp_path / f"{source.source_id}.txt",
                text=text,
                parser_name="plain_text",
                char_count=len(text),
            )
        )

    chunks = []
    for document in clean_documents:
        source = next(source for source in sources if source.source_id == document.source_id)
        chunks.extend(chunk_clean_document(document, source, max_chars=300, overlap_chars=0, min_chars=80))
    filtered_chunks = filter_chunks(chunks, min_chars=80, min_domain_terms=2)
    ranked_chunks = rank_chunks_bm25(filtered_chunks, plan.queries, top_k_per_query=3)
    evidence_items = build_evidence_items(ranked_chunks, max_items=8)
    summary = build_evaluation_summary(
        plan=plan,
        sources=sources,
        clean_documents=clean_documents,
        chunks=chunks,
        filtered_chunks=filtered_chunks,
        evidence_items=evidence_items,
    )
    report_markdown = render_markdown_report(
        topic=plan.topic,
        evidence_items=evidence_items,
        evaluation_summary=summary,
    )
    gate = run_quality_gate(
        evidence_items=evidence_items,
        evaluation_summary=summary,
        report_markdown=report_markdown,
        min_clean_documents=5,
        min_evidence_items=3,
        min_evidence_sources=2,
    )

    assert summary["clean_document_count"] == 5
    assert "## Evidence table" in report_markdown
    assert "## Unknowns" in report_markdown
    assert gate.status in {"pass", "warn"}
