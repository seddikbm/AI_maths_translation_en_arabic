from __future__ import annotations

import re


ARABIC_CHARS = re.compile(r"[\u0600-\u06FF]")
WHITESPACE = re.compile(r"\s+")
SEGMENT_SPLIT = re.compile(r"(?<=[.!?؟])\s+|\n{2,}")


def normalize_whitespace(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def split_segments(text: str) -> list[str]:
    normalized = text.replace("\r", "\n")
    chunks = [normalize_whitespace(chunk) for chunk in SEGMENT_SPLIT.split(normalized)]
    return [chunk for chunk in chunks if 10 <= len(chunk) <= 1500]


def detect_language(text: str) -> str:
    arabic_hits = len(ARABIC_CHARS.findall(text))
    return "ar" if arabic_hits >= max(1, len(text) // 8) else "en"


def shape_arabic_text(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:
        return text
    return get_display(arabic_reshaper.reshape(text))
