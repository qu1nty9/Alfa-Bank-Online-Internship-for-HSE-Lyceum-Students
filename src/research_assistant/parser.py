"""Raw document parsing and lightweight text cleaning."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from .models import CleanDocument, ParseResult, RawDocument, SourceCandidate


class ParseError(RuntimeError):
    """Raised when a raw document cannot be parsed into useful text."""


def parse_raw_document(
    raw_document: RawDocument,
    source: SourceCandidate,
    clean_dir: str | Path,
) -> CleanDocument:
    """Extract clean text from a raw HTML, text, or PDF document."""

    raw_path = raw_document.path
    suffix = raw_path.suffix.lower()

    if suffix == ".pdf" or _is_pdf(raw_document):
        text = extract_pdf_text(raw_path)
        parser_name = "pypdf"
    elif suffix == ".md" or _is_markdown(raw_document):
        text = raw_path.read_text(encoding="utf-8", errors="ignore")
        parser_name = "markdown_text"
    elif suffix == ".txt" or _is_plain_text(raw_document):
        text = raw_path.read_text(encoding="utf-8", errors="ignore")
        parser_name = "plain_text"
    else:
        html = raw_path.read_text(encoding="utf-8", errors="ignore")
        text, parser_name = extract_html_text_with_parser(html)

    clean_text = normalize_whitespace(text)
    if not clean_text:
        raise ParseError(f"No clean text extracted for {source.source_id}")

    clean_path = clean_document_path(source, clean_dir)
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.write_text(clean_text, encoding="utf-8")

    return CleanDocument(
        source_id=source.source_id,
        title=source.title,
        url=source.url,
        path=clean_path,
        text=clean_text,
        content_type=raw_document.content_type,
        parser_name=parser_name,
        char_count=len(clean_text),
    )


def parse_raw_documents(
    raw_documents: list[RawDocument],
    sources: list[SourceCandidate],
    clean_dir: str | Path,
) -> list[CleanDocument]:
    """Parse several raw documents, matching them by source_id."""

    sources_by_id = {source.source_id: source for source in sources}
    clean_documents: list[CleanDocument] = []
    for raw_document in raw_documents:
        source = sources_by_id.get(raw_document.source_id)
        if source is None:
            raise ParseError(f"Missing source metadata for {raw_document.source_id}")
        clean_documents.append(parse_raw_document(raw_document, source, clean_dir))
    return clean_documents


def parse_raw_documents_safe(
    raw_documents: list[RawDocument],
    sources: list[SourceCandidate],
    clean_dir: str | Path,
) -> list[ParseResult]:
    """Parse several raw documents and keep going when individual sources fail."""

    sources_by_id = {source.source_id: source for source in sources}
    results: list[ParseResult] = []
    for raw_document in raw_documents:
        source = sources_by_id.get(raw_document.source_id)
        if source is None:
            results.append(
                ParseResult(
                    source_id=raw_document.source_id,
                    ok=False,
                    error=f"Missing source metadata for {raw_document.source_id}",
                )
            )
            continue

        try:
            clean_document = parse_raw_document(raw_document, source, clean_dir)
        except ParseError as exc:
            results.append(ParseResult(source_id=raw_document.source_id, ok=False, error=str(exc)))
        else:
            results.append(
                ParseResult(
                    source_id=raw_document.source_id,
                    ok=True,
                    clean_document=clean_document,
                )
            )
    return results


def clean_document_path(source: SourceCandidate, clean_dir: str | Path) -> Path:
    """Return the stable clean-text path for a source."""

    return Path(clean_dir) / f"{source.source_id}.txt"


def extract_html_text(html: str) -> str:
    """Extract visible text from HTML with optional boilerplate cleanup."""

    text, _parser_name = extract_html_text_with_parser(html)
    return text


def extract_html_text_with_parser(html: str) -> tuple[str, str]:
    """Extract visible text from HTML and return the parser that worked."""

    for parser_name, extractor in [
        ("trafilatura_html", _extract_html_with_trafilatura),
        ("beautifulsoup_html", _extract_html_with_beautifulsoup),
        ("stdlib_html_parser", _extract_html_with_stdlib),
    ]:
        try:
            text = normalize_whitespace(extractor(html))
        except Exception:
            continue
        if _has_enough_text(text):
            return text, parser_name

    text = normalize_whitespace(_extract_html_with_stdlib(html))
    return text, "stdlib_html_parser"


def _extract_html_with_trafilatura(html: str) -> str:
    try:
        from trafilatura import extract
    except ModuleNotFoundError as exc:
        raise ParseError("trafilatura is not available") from exc

    extracted = extract(
        _strip_html_noise_tags(html),
        include_comments=False,
        include_formatting=False,
        include_images=False,
        include_links=False,
        include_tables=True,
    )
    return extracted or ""


def _extract_html_with_beautifulsoup(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ModuleNotFoundError as exc:
        raise ParseError("beautifulsoup4 is not available") from exc

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "header", "footer"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    return root.get_text("\n")


def _extract_html_with_stdlib(html: str) -> str:
    """Extract visible text from HTML using only the Python standard library."""

    parser = _VisibleTextHTMLParser()
    parser.feed(html)
    parser.close()
    return "\n".join(parser.text_parts)


def _strip_html_noise_tags(html: str) -> str:
    cleaned = html
    for tag in ["script", "style", "noscript", "svg", "nav", "header", "footer"]:
        cleaned = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            " ",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return cleaned


def extract_pdf_text(path: str | Path) -> str:
    """Extract text from a PDF through pypdf."""

    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise ParseError("pypdf is required to parse PDF sources") from exc

    reader = PdfReader(str(path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    return normalize_whitespace("\n\n".join(page_texts))


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace while preserving paragraph-ish line breaks."""

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    non_empty_lines = _dedupe_repeated_lines([line for line in lines if line])
    return "\n".join(non_empty_lines).strip()


def _dedupe_repeated_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    seen_short_lines: dict[str, int] = {}
    previous_signature = ""
    for line in lines:
        signature = line.lower()
        if signature == previous_signature:
            continue
        if len(line) <= 140:
            seen_count = seen_short_lines.get(signature, 0)
            if seen_count >= 2:
                continue
            seen_short_lines[signature] = seen_count + 1
        deduped.append(line)
        previous_signature = signature
    return deduped


def _has_enough_text(text: str) -> bool:
    return len(text) >= 80 or len(text.split()) >= 12


def _is_pdf(raw_document: RawDocument) -> bool:
    return (raw_document.content_type or "").split(";", 1)[0].strip().lower() == "application/pdf"


def _is_plain_text(raw_document: RawDocument) -> bool:
    return (raw_document.content_type or "").split(";", 1)[0].strip().lower() == "text/plain"


def _is_markdown(raw_document: RawDocument) -> bool:
    return (raw_document.content_type or "").split(";", 1)[0].strip().lower() in {
        "text/markdown",
        "text/x-markdown",
    }


class _VisibleTextHTMLParser(HTMLParser):
    """Small visible-text extractor for MVP demos without external parsers."""

    _SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer"}
    _BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
        "ol",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS and self.text_parts:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS and self.text_parts:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = data.strip()
        if value:
            self.text_parts.append(value)
