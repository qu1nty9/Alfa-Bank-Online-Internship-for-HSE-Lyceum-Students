"""Baseline chunk filtering and BM25 ranking."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable

from .chunker import simple_tokenize
from .models import SearchQuery, TextChunk

DOMAIN_TERMS = {
    "bank",
    "banking",
    "banks",
    "financial",
    "finance",
    "customer",
    "customers",
    "clv",
    "cltv",
    "lifetime",
    "value",
    "retention",
    "attrition",
    "personalization",
    "personalisation",
    "profitability",
    "margin",
    "product",
    "products",
    "channel",
    "channels",
    "risk",
    "privacy",
    "explainability",
}

NOISE_TERMS = {
    "cookie",
    "cookies",
    "subscribe",
    "newsletter",
    "advertisement",
    "privacy policy",
    "terms of use",
}

STRONG_NOISE_TERMS = {
    "i consent",
    "marketing communications",
    "provider of this website",
    "select one",
    "virgin islands",
    "terms of use",
    "cookie preferences",
}


def filter_chunks(
    chunks: list[TextChunk],
    *,
    min_chars: int = 200,
    min_domain_terms: int = 2,
    domain_terms: Iterable[str] | None = None,
) -> list[TextChunk]:
    """Remove short, duplicate, and obviously non-domain chunks."""

    filtered: list[TextChunk] = []
    seen_signatures: set[str] = set()
    active_domain_terms = set(domain_terms or DOMAIN_TERMS)

    for chunk in chunks:
        if chunk.char_count < min_chars:
            continue
        if _looks_like_noise(chunk.text):
            continue

        tokens = set(simple_tokenize(chunk.text))
        if min_domain_terms > 0 and len(tokens & active_domain_terms) < min_domain_terms:
            continue

        signature = _chunk_signature(chunk.text)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        filtered.append(chunk)

    return filtered


def rank_chunks_bm25(
    chunks: list[TextChunk],
    queries: list[SearchQuery],
    *,
    top_k_per_query: int = 5,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[TextChunk, SearchQuery, float]]:
    """Rank chunks for each query with a compact BM25 implementation."""

    if not chunks or not queries:
        return []

    tokenized_chunks = [simple_tokenize(chunk.text) for chunk in chunks]
    chunk_term_counts = [Counter(tokens) for tokens in tokenized_chunks]
    chunk_lengths = [len(tokens) for tokens in tokenized_chunks]
    average_length = sum(chunk_lengths) / len(chunk_lengths)
    document_frequencies = _document_frequencies(tokenized_chunks)
    total_documents = len(chunks)

    ranked: list[tuple[TextChunk, SearchQuery, float]] = []
    for query in queries:
        query_terms = simple_tokenize(query.query)
        scored_chunks = [
            (
                chunk,
                _bm25_score(
                    query_terms,
                    term_counts,
                    length,
                    average_length,
                    document_frequencies,
                    total_documents,
                    k1=k1,
                    b=b,
                ),
            )
            for chunk, term_counts, length in zip(chunks, chunk_term_counts, chunk_lengths)
        ]

        for chunk, score in sorted(scored_chunks, key=lambda item: item[1], reverse=True)[:top_k_per_query]:
            if score > 0:
                ranked.append((chunk, query, score))

    return ranked


def _document_frequencies(tokenized_chunks: list[list[str]]) -> Counter[str]:
    frequencies: Counter[str] = Counter()
    for tokens in tokenized_chunks:
        frequencies.update(set(tokens))
    return frequencies


def _bm25_score(
    query_terms: list[str],
    term_counts: Counter[str],
    document_length: int,
    average_length: float,
    document_frequencies: Counter[str],
    total_documents: int,
    *,
    k1: float,
    b: float,
) -> float:
    score = 0.0
    for term in query_terms:
        term_frequency = term_counts.get(term, 0)
        if term_frequency == 0:
            continue

        document_frequency = document_frequencies.get(term, 0)
        idf = math.log(1 + (total_documents - document_frequency + 0.5) / (document_frequency + 0.5))
        denominator = term_frequency + k1 * (1 - b + b * document_length / average_length)
        score += idf * (term_frequency * (k1 + 1)) / denominator
    return score


def _looks_like_noise(text: str) -> bool:
    lower_text = text.lower()
    if any(term in lower_text for term in STRONG_NOISE_TERMS):
        return True
    if any(term in lower_text for term in NOISE_TERMS) and len(text) < 600:
        return True
    return False


def _chunk_signature(text: str, *, token_count: int = 40) -> str:
    tokens = simple_tokenize(text)
    return " ".join(tokens[:token_count])
