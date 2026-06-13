"""Language selection helpers for report generation."""

from __future__ import annotations

import re
from typing import Literal

ReportLanguage = Literal["en", "ru"]

_CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
_ASCII_LATIN_RE = re.compile(r"[A-Za-z]")


def detect_report_language(text: str) -> ReportLanguage:
    """Choose the report language from the user's topic text.

    English-only topics stay in English. Mixed English and Cyrillic topics are
    rendered in Russian because the non-English part carries the user's desired
    business language in the current product scope.
    """

    compact_text = text.strip()
    if _CYRILLIC_RE.search(compact_text):
        return "ru"
    if _ASCII_LATIN_RE.search(compact_text):
        return "en"
    return "en"
