from __future__ import annotations

import re


ARABIC_CHARS = re.compile(r"[\u0600-\u06FF]")
WHITESPACE = re.compile(r"\s+")
PARAGRAPH_SPLIT = re.compile(r"\n{2,}")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u061f])\s+")
MAX_SEGMENT_CHARS = 1200


def normalize_whitespace(text: str) -> str:
    return WHITESPACE.sub(" ", text).strip()


def split_segments(text: str, max_chars: int = MAX_SEGMENT_CHARS) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []

    segments: list[str] = []
    for paragraph in PARAGRAPH_SPLIT.split(normalized):
        paragraph = normalize_whitespace(paragraph)
        if paragraph:
            segments.extend(_pack_sentences(SENTENCE_SPLIT.split(paragraph), max_chars))
    return segments


def _pack_sentences(sentences: list[str], max_chars: int) -> list[str]:
    packed: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = normalize_whitespace(sentence)
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                packed.append(current)
                current = ""
            packed.extend(_split_by_words(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            packed.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        packed.append(current)
    return packed


def _split_by_words(text: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = ""

    for word in text.split():
        if len(word) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(word[index : index + max_chars] for index in range(0, len(word), max_chars))
            continue

        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


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
