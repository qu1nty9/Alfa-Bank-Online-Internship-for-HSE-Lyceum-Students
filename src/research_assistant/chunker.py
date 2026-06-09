"""Chunk clean documents into stable text fragments."""

from __future__ import annotations

import re

from .models import CleanDocument, SourceCandidate, TextChunk


def chunk_clean_document(
    document: CleanDocument,
    source: SourceCandidate,
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    min_chars: int = 160,
) -> list[TextChunk]:
    """Split one clean document into paragraph-aware chunks."""

    if max_chars <= overlap_chars:
        raise ValueError("max_chars must be greater than overlap_chars")

    paragraphs = _split_paragraphs(document.text)
    chunks: list[TextChunk] = []
    current_parts: list[str] = []
    current_start = 0
    cursor = 0

    for paragraph in paragraphs:
        paragraph_start = document.text.find(paragraph, cursor)
        if paragraph_start == -1:
            paragraph_start = cursor
        paragraph_end = paragraph_start + len(paragraph)

        candidate = "\n\n".join([*current_parts, paragraph]).strip()
        if current_parts and len(candidate) > max_chars:
            chunk_text = "\n\n".join(current_parts).strip()
            _append_chunk(chunks, document, source, chunk_text, current_start)
            overlap = _tail_overlap(chunk_text, overlap_chars)
            current_parts = [overlap, paragraph] if overlap else [paragraph]
            current_start = max(0, paragraph_start - len(overlap))
        else:
            if not current_parts:
                current_start = paragraph_start
            current_parts.append(paragraph)

        cursor = paragraph_end

    if current_parts:
        chunk_text = "\n\n".join(current_parts).strip()
        _append_chunk(chunks, document, source, chunk_text, current_start)

    return [chunk for chunk in chunks if chunk.char_count >= min_chars]


def chunk_clean_documents(
    documents: list[CleanDocument],
    sources: list[SourceCandidate],
    *,
    max_chars: int = 1200,
    overlap_chars: int = 150,
    min_chars: int = 160,
) -> list[TextChunk]:
    """Chunk several clean documents matched by source_id."""

    sources_by_id = {source.source_id: source for source in sources}
    chunks: list[TextChunk] = []
    for document in documents:
        source = sources_by_id.get(document.source_id)
        if source is None:
            raise ValueError(f"Missing source metadata for {document.source_id}")
        chunks.extend(
            chunk_clean_document(
                document,
                source,
                max_chars=max_chars,
                overlap_chars=overlap_chars,
                min_chars=min_chars,
            )
        )
    return chunks


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{1,}", text)]
    return [paragraph for paragraph in paragraphs if paragraph]


def _append_chunk(
    chunks: list[TextChunk],
    document: CleanDocument,
    source: SourceCandidate,
    text: str,
    start_char: int,
) -> None:
    if not text:
        return

    chunk_number = len(chunks) + 1
    end_char = start_char + len(text)
    chunks.append(
        TextChunk(
            source_id=document.source_id,
            chunk_id=f"{document.source_id}_chunk_{chunk_number:03d}",
            text=text,
            title=document.title,
            url=document.url,
            source_type=source.source_type,
            research_block=source.research_block,
            start_char=start_char,
            end_char=end_char,
            char_count=len(text),
            token_count=len(simple_tokenize(text)),
        )
    )


def _tail_overlap(text: str, overlap_chars: int) -> str:
    if overlap_chars <= 0:
        return ""
    return text[-overlap_chars:].strip()


def simple_tokenize(text: str) -> list[str]:
    """Tokenize English/Russian-ish text for baseline filters and BM25."""

    return re.findall(r"[a-zA-Zа-яА-Я0-9]+", text.lower())
