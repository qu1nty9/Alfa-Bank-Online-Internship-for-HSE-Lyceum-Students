import hashlib
from pathlib import Path

from research_assistant.chunker import chunk_clean_document
from research_assistant.claims import build_claim_items, write_claims_csv, write_claims_jsonl
from research_assistant.collector import (
    build_sources_from_urls,
    group_sources_by_research_block,
    load_seed_sources,
)
from research_assistant.config import PipelineConfig
from research_assistant.evidence import build_evidence_items, write_evidence_csv
from research_assistant.evaluation import build_evaluation_summary
from research_assistant.fetcher import fetch_sources_safe, raw_document_path
from research_assistant.filtering import filter_chunks, rank_chunks_bm25
from research_assistant.knowledge_graph import build_knowledge_graph
from research_assistant.llm_gateway import (
    LLMGatewayConfig,
    LLMGatewayError,
    build_llm_gateway,
    default_llm_gateway_metadata,
    llm_gateway_config_from_env,
)
from research_assistant.models import CleanDocument, RawDocument, SourceCandidate, SourceType
from research_assistant.parser import extract_html_text, parse_raw_document, parse_raw_documents_safe
from research_assistant.pipeline import run_research_pipeline, run_research_pipeline_with_sources
from research_assistant.planner import build_cltv_research_plan, build_research_plan
from research_assistant.quality_gate import run_quality_gate
from research_assistant.report import render_markdown_report
from research_assistant.sensitivity import check_query_sensitivity
from research_assistant.source_policy import (
    SourcePolicyConfig,
    filter_sources_by_policy,
    summarize_source_policy,
)
from research_assistant.source_discovery import SourceDiscoveryConfig, discover_public_sources

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cltv_research_plan_has_required_blocks() -> None:
    plan = build_cltv_research_plan()

    assert plan.topic == "CLTV in foreign banks"
    assert "banking_use_cases" in plan.blocks
    assert len(plan.queries) >= 5


def test_generic_research_plan_uses_arbitrary_topic() -> None:
    plan = build_research_plan("AI fraud detection in insurance")

    assert plan.topic == "AI fraud detection in insurance"
    assert "definition_and_context" in plan.blocks
    assert any("AI fraud detection in insurance" in query.query for query in plan.queries)


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


def test_user_sources_can_be_built_from_urls() -> None:
    sources = build_sources_from_urls(
        ["https://example.com/research", "https://example.com/research"],
        topic="Open banking fraud detection",
    )

    expected_id = "user_" + hashlib.sha256(b"https://example.com/research").hexdigest()[:12]
    assert [source.source_id for source in sources] == [expected_id]
    assert sources[0].publisher == "example.com"
    assert sources[0].research_block == "definition_and_context"


def test_public_source_discovery_uses_public_api_payloads(monkeypatch) -> None:
    def fake_load_json(url: str, timeout_seconds: int) -> dict:
        if "wikipedia" in url:
            return {"query": {"search": [{"title": "Fraud detection"}]}}
        return {
            "results": [
                {
                    "title": "Insurance fraud detection survey",
                    "primary_location": {
                        "landing_page_url": "https://example.org/fraud-survey"
                    },
                }
            ]
        }

    monkeypatch.setattr("research_assistant.source_discovery._load_json", fake_load_json)

    sources = discover_public_sources(
        "AI fraud detection in insurance",
        config=SourceDiscoveryConfig(
            max_sources=4,
            include_arxiv=False,
            include_crossref=False,
            include_searxng=False,
        ),
    )

    wiki_hash = hashlib.sha256(
        b"https://en.wikipedia.org/wiki/Fraud_detection"
    ).hexdigest()[:12]
    openalex_hash = hashlib.sha256(b"https://example.org/fraud-survey").hexdigest()[:12]
    assert [source.source_id for source in sources] == [
        f"wiki_{wiki_hash}",
        f"openalex_{openalex_hash}",
    ]
    assert [str(source.url) for source in sources] == [
        "https://en.wikipedia.org/wiki/Fraud_detection",
        "https://example.org/fraud-survey",
    ]
    assert sources[0].source_type.value == "encyclopedia"
    assert sources[1].source_type.value == "research_index"
    assert sources[0].research_block == "definition_and_context"

    repeat_sources = discover_public_sources(
        "AI fraud detection in insurance",
        config=SourceDiscoveryConfig(
            max_sources=4,
            include_arxiv=False,
            include_crossref=False,
            include_searxng=False,
        ),
    )
    assert [source.source_id for source in repeat_sources] == [
        source.source_id for source in sources
    ]


def test_source_policy_config_filters_by_ids_types_and_domains() -> None:
    sources = load_seed_sources(PROJECT_ROOT / "data/seed_sources/cltv_sources_template.csv")
    policy = SourcePolicyConfig(
        allowed_source_types=["consulting"],
        allow_unlisted_public_sources=False,
        allowed_source_ids=["seed_003"],
        allowed_domains=["bcg.com"],
    )

    summary = summarize_source_policy(
        sources,
        use_live_fetch=False,
        fetch_limit=None,
        policy=policy,
    )

    assert summary["policy_version"] == "source-policy-v1"
    assert summary["allowed_source_ids"] == ["seed_003"]
    assert summary["allowed_source_count"] == 1
    assert "seed_001" in summary["blocked_source_ids"]
    assert [source.source_id for source in filter_sources_by_policy(sources, policy)] == [
        "seed_003"
    ]
    assert any(
        decision["source_id"] == "seed_001" and not decision["allowed"]
        for decision in summary["source_decisions"]
    )


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


def test_parse_markdown_upload_as_clean_text(tmp_path) -> None:
    source = SourceCandidate(
        source_id="upload_test_001",
        url="https://local.upload/run_test/research.md",
        title="research.md",
        source_type=SourceType.UPLOADED_DOCUMENT,
        publisher="local upload",
        research_block="definition_and_context",
        status="ready",
    )
    raw_path = tmp_path / "research.md"
    raw_path.write_text(
        "# Fraud analytics\n\nAI fraud detection in insurance uses claims signals.",
        encoding="utf-8",
    )
    raw_document = RawDocument(
        source_id=source.source_id,
        url=source.url,
        path=raw_path,
        content_type="text/markdown",
    )

    clean_document = parse_raw_document(raw_document, source, tmp_path / "clean")

    assert clean_document.parser_name == "markdown_text"
    assert "AI fraud detection" in clean_document.text


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
    claim_items = build_claim_items(evidence_items)
    csv_path = write_evidence_csv(evidence_items, tmp_path / "evidence.csv")
    claims_csv_path = write_claims_csv(claim_items, tmp_path / "claims.csv")
    claims_jsonl_path = write_claims_jsonl(claim_items, tmp_path / "claims.jsonl")

    assert chunks
    assert filtered_chunks
    assert ranked_chunks
    assert evidence_items
    assert claim_items
    assert claim_items[0].evidence_ids == [
        f"{evidence_items[0].source_id}/{evidence_items[0].chunk_id}"
    ]
    assert evidence_items[0].chunk_id.startswith(source.source_id)
    assert csv_path.exists()
    assert claims_csv_path.exists()
    assert claims_jsonl_path.exists()


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
    assert summary["analyzed_sources"]
    assert summary["interpretability_summary"]["source_diversity"] in {"medium", "high"}
    assert "## Краткий ответ" in report_markdown
    assert "## Паспорт результата" in report_markdown
    assert "## Полный отчет по источникам и ресурсам" in report_markdown
    assert "## Утверждения и доказательства" in report_markdown
    assert "## Knowledge graph links" in report_markdown
    assert "## Evidence table" in report_markdown
    assert "## Unknowns" in report_markdown
    assert gate.status in {"pass", "warn"}


def test_knowledge_graph_links_claims_evidence_and_sources() -> None:
    graph = build_knowledge_graph(
        evidence_items=[
            {
                "source_id": "upload_test_001",
                "chunk_id": "upload_test_001_chunk_001",
                "source_type": "uploaded_document",
                "research_block": "definition_and_context",
                "text": "AI fraud detection in insurance uses claim history.",
            }
        ],
        claim_items=[
            {
                "claim_id": "claim_001",
                "confidence": "high",
                "evidence_ids": ["upload_test_001/upload_test_001_chunk_001"],
                "claim_text": "AI fraud detection has evidence in the uploaded file.",
            }
        ],
    )

    assert graph["summary"]["source_count"] == 1
    assert graph["summary"]["edge_count"] == 2
    assert any(edge["relation"] == "supported_by" for edge in graph["edges"])


def test_sensitivity_blocks_personal_data() -> None:
    result = check_query_sensitivity("CLTV for client ivan@example.com")

    assert result.decision == "block"
    assert result.allowed is False


def test_default_llm_gateway_metadata_is_offline() -> None:
    metadata = default_llm_gateway_metadata()

    assert metadata["mode"] == "offline_template"
    assert metadata["provider"] == "offline"
    assert metadata["model"] == "template-report-v1"
    assert metadata["external_llm_calls"] is False


def test_openai_compatible_gateway_requires_explicit_external_enablement() -> None:
    gateway = build_llm_gateway(
        LLMGatewayConfig(
            mode="openai_compatible",
            provider="corporate_llm",
            model="demo-model",
            endpoint_url="https://llm-gateway.example.com/v1/chat/completions",
            external_calls_enabled=False,
        )
    )

    metadata = gateway.metadata()
    assert metadata.mode == "openai_compatible"
    assert metadata.provider == "corporate_llm"
    assert metadata.external_llm_calls is False

    try:
        gateway.synthesize_report("CLTV in foreign banks", [])
    except LLMGatewayError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Expected disabled external call to raise LLMGatewayError")


def test_llm_gateway_env_profile_supports_local_qwen(monkeypatch) -> None:
    monkeypatch.setenv("LLM_GATEWAY_MODE", "openai_compatible")
    monkeypatch.setenv("LLM_PROVIDER", "local_qwen")
    monkeypatch.setenv("LLM_MODEL", "qwen3:1.7b")
    monkeypatch.setenv("LLM_ENDPOINT_URL", "http://localhost:11434/v1/chat/completions")
    monkeypatch.setenv("LLM_EXTERNAL_CALLS_ENABLED", "true")

    config = llm_gateway_config_from_env()
    metadata = build_llm_gateway(config).metadata()

    assert config.mode == "openai_compatible"
    assert config.provider == "local_qwen"
    assert config.model == "qwen3:1.7b"
    assert metadata.external_llm_calls is True
    assert metadata.endpoint_url == "http://localhost:11434/v1/chat/completions"


def test_llm_gateway_env_profile_supports_alfagen(monkeypatch) -> None:
    monkeypatch.setenv("LLM_GATEWAY_MODE", "openai_compatible")
    monkeypatch.setenv("LLM_PROVIDER", "alfagen")
    monkeypatch.setenv("LLM_MODEL", "alfagen-default")
    monkeypatch.setenv("LLM_ENDPOINT_URL", "https://alfagen.example.com/v1/chat/completions")
    monkeypatch.setenv("LLM_API_KEY_ENV_VAR", "ALFAGEN_API_KEY")
    monkeypatch.setenv("ALFAGEN_API_KEY", "test-token")

    metadata = default_llm_gateway_metadata()

    assert metadata["mode"] == "openai_compatible"
    assert metadata["provider"] == "alfagen"
    assert metadata["api_key_env_var"] == "ALFAGEN_API_KEY"
    assert metadata["api_key_configured"] is True
    assert metadata["external_llm_calls"] is False


def test_llm_gateway_env_profile_supports_gigachat(monkeypatch) -> None:
    monkeypatch.setenv("LLM_GATEWAY_MODE", "gigachat")
    monkeypatch.setenv("LLM_ENDPOINT_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
    monkeypatch.setenv("GIGACHAT_ACCESS_TOKEN", "test-token")

    config = llm_gateway_config_from_env()
    metadata = build_llm_gateway(config).metadata()

    assert config.mode == "gigachat"
    assert config.provider == "gigachat"
    assert config.api_key_env_var == "GIGACHAT_ACCESS_TOKEN"
    assert metadata.api_key_configured is True
    assert metadata.external_llm_calls is False


def test_modular_pipeline_runs_offline_on_clean_fixtures(tmp_path) -> None:
    seed_path = tmp_path / "data" / "seed_sources" / "cltv_sources_template.csv"
    clean_dir = tmp_path / "data" / "clean"
    raw_dir = tmp_path / "data" / "raw"
    reports_dir = tmp_path / "reports"
    seed_path.parent.mkdir(parents=True)
    clean_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    seed_path.write_text(
        "\n".join(
            [
                "source_id,url,title,source_type,publisher,research_block,language,status,notes",
                "seed_001,https://example.com/one,One,vendor,Example,definition_and_business_value,en,ready,",
                "seed_002,https://example.com/two,Two,academic,Example,calculation_methods,en,ready,",
                "seed_003,https://example.com/three,Three,consulting,Example,required_data,en,ready,",
                "seed_004,https://example.com/four,Four,consulting,Example,banking_use_cases,en,ready,",
                "seed_005,https://example.com/five,Five,consulting,Example,risks_and_limitations,en,ready,",
            ]
        ),
        encoding="utf-8",
    )
    fixture_texts = {
        "seed_001": "Customer lifetime value banking use cases help banks prioritize retention and profitability.",
        "seed_002": "Customer lifetime value calculation banking retention probability margin products risk.",
        "seed_003": "Bank customer lifetime value data requirements transactions products campaigns channels.",
        "seed_004": "CLTV next best action banking personalization retention cross sell customer analytics.",
        "seed_005": "Customer lifetime value banking privacy bias explainability risks responsible AI.",
    }
    for source_id, text in fixture_texts.items():
        (clean_dir / f"{source_id}.txt").write_text(text, encoding="utf-8")

    config = PipelineConfig(
        project_root=tmp_path,
        seed_sources_path=seed_path,
        raw_dir=raw_dir,
        clean_dir=clean_dir,
        reports_dir=reports_dir,
        source_strategy="seed_sources",
        use_live_fetch=False,
        chunk_min_chars=60,
        filter_min_chars=60,
        min_clean_documents=5,
        min_evidence_items=3,
        min_evidence_sources=2,
    ).resolved()

    result = run_research_pipeline("CLTV in foreign banks", config)

    assert result.sensitivity.decision == "allow"
    assert result.quality_gate.status in {"pass", "warn"}
    assert result.evaluation_summary["clean_document_count"] == 5
    assert result.model_gateway_metadata["mode"] == "offline_template"
    assert result.model_gateway_metadata["synthesis_status"] == "not_requested"
    assert result.report_path is not None
    assert result.report_path.exists()
    assert result.claim_items
    assert result.claims_csv_path is not None
    assert result.claims_csv_path.exists()
    assert result.claims_jsonl_path is not None
    assert result.claims_jsonl_path.exists()


def test_generic_pipeline_without_sources_fails_without_cltv_leakage(tmp_path) -> None:
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir(parents=True)
    config = PipelineConfig(
        project_root=PROJECT_ROOT,
        raw_dir=tmp_path / "raw",
        clean_dir=clean_dir,
        reports_dir=tmp_path / "reports",
        use_live_fetch=False,
        auto_discover_sources=False,
    ).resolved()

    result = run_research_pipeline("AI fraud detection in insurance", config)

    assert result.quality_gate.status == "fail"
    assert result.evaluation_summary["planner_mode"] == "generic"
    assert result.evaluation_summary["source_mode"] == "no_topic_sources"
    assert result.evaluation_summary["evidence_item_count"] == 0
    assert result.report_path is not None
    assert result.report_path.read_text(encoding="utf-8").startswith(
        "# AI fraud detection in insurance"
    )


def test_cltv_pipeline_without_discovery_does_not_use_seed_fallback(tmp_path) -> None:
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir(parents=True)
    config = PipelineConfig(
        project_root=PROJECT_ROOT,
        raw_dir=tmp_path / "raw",
        clean_dir=clean_dir,
        reports_dir=tmp_path / "reports",
        use_live_fetch=False,
        auto_discover_sources=False,
    ).resolved()

    result = run_research_pipeline("CLTV in foreign banks", config)

    assert result.quality_gate.status == "fail"
    assert result.evaluation_summary["planner_mode"] == "generic"
    assert result.evaluation_summary["source_mode"] == "no_topic_sources"
    assert result.evaluation_summary["source_candidate_count"] == 0
    assert result.evaluation_summary["clean_document_count"] == 0


def test_generic_pipeline_runs_with_user_provided_cached_sources(tmp_path) -> None:
    clean_dir = tmp_path / "clean"
    reports_dir = tmp_path / "reports"
    clean_dir.mkdir(parents=True)
    source = SourceCandidate(
        source_id="user_001",
        url="https://example.com/ai-fraud",
        title="AI fraud detection in insurance report",
        source_type=SourceType.OTHER,
        publisher="Example",
        research_block="methods_and_approaches",
        language="en",
        status="ready",
    )
    (clean_dir / "user_001.txt").write_text(
        (
            "AI fraud detection in insurance uses anomaly detection, graph analytics, "
            "claims history, payment behavior, identity signals, governance controls, "
            "and model monitoring to reduce suspicious claims and operational risk."
        ),
        encoding="utf-8",
    )
    config = PipelineConfig(
        project_root=tmp_path,
        raw_dir=tmp_path / "raw",
        clean_dir=clean_dir,
        reports_dir=reports_dir,
        use_live_fetch=False,
        chunk_min_chars=40,
        filter_min_chars=40,
        min_clean_documents=1,
        min_evidence_items=1,
        min_evidence_sources=1,
    ).resolved()

    result = run_research_pipeline_with_sources(
        "AI fraud detection in insurance",
        config=config,
        source_candidates=[source],
    )

    assert result.quality_gate.status in {"pass", "warn"}
    assert result.evaluation_summary["planner_mode"] == "generic"
    assert result.evaluation_summary["source_mode"] == "request_sources"
    assert result.evaluation_summary["evidence_item_count"] >= 1
    assert result.report_path is not None
    assert result.report_path.name == "report_ai_fraud_detection_in_insurance.md"
