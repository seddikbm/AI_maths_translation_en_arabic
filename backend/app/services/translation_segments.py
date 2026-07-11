from __future__ import annotations

import re
from typing import Any

from ..schemas import TranslationDirection
from ..utils.text_utils import split_segments


TRANSLATION_BATCH_SIZE = 4
LINE_BREAKS = re.compile(r"(\n+)")
MATH_PLACEHOLDER = re.compile(r"(<MATH_\d+>)")


def translate_segments(
    model_service: Any,
    segments: list[str],
    direction: TranslationDirection,
    protected_map: dict[str, str],
    batch_size: int = TRANSLATION_BATCH_SIZE,
) -> list[str]:
    translated: list[str | None] = [None] * len(segments)
    batch_slots: list[int] = []
    batch: list[str] = []

    def flush_batch() -> None:
        if not batch:
            return
        batch_translations = model_service.translate_texts(batch, direction)
        for slot, source, translation in zip(batch_slots, batch, batch_translations, strict=False):
            placeholders = _segment_placeholders(source, protected_map)
            if placeholders and not all(placeholder in translation for placeholder in placeholders):
                translation = _translate_segment_pieces(model_service, source, direction, protected_map, batch_size)
            translated[slot] = translation
        batch.clear()
        batch_slots.clear()

    for index, segment in enumerate(segments):
        if segment.strip() in protected_map:
            flush_batch()
            translated[index] = segment.strip()
            continue

        batch.append(segment)
        batch_slots.append(index)
        if len(batch) >= batch_size:
            flush_batch()

    flush_batch()
    return [item or "" for item in translated]


def _segment_placeholders(segment: str, protected_map: dict[str, str]) -> list[str]:
    return [placeholder for placeholder in MATH_PLACEHOLDER.findall(segment) if placeholder in protected_map]


def _translate_segment_pieces(
    model_service: Any,
    segment: str,
    direction: TranslationDirection,
    protected_map: dict[str, str],
    batch_size: int,
) -> str:
    output_parts: list[str | None] = []
    pending_slots: list[int] = []
    batch: list[str] = []

    def flush_batch() -> None:
        if not batch:
            return
        for slot, translation in zip(pending_slots, model_service.translate_texts(batch, direction), strict=False):
            output_parts[slot] = translation
        batch.clear()
        pending_slots.clear()

    for piece in MATH_PLACEHOLDER.split(segment):
        if not piece:
            continue
        if piece in protected_map or not piece.strip():
            output_parts.append(piece)
            continue
        output_parts.append(None)
        pending_slots.append(len(output_parts) - 1)
        batch.append(piece)
        if len(batch) >= batch_size:
            flush_batch()

    flush_batch()
    return "".join(part or "" for part in output_parts).strip()


def translate_text_preserving_breaks(
    model_service: Any,
    text: str,
    direction: TranslationDirection,
    protected_map: dict[str, str],
    batch_size: int = TRANSLATION_BATCH_SIZE,
) -> str:
    output_parts: list[str | None] = []
    segment_groups: list[tuple[int, int, int]] = []
    flat_segments: list[str] = []

    for piece in LINE_BREAKS.split(text):
        if not piece:
            continue
        if LINE_BREAKS.fullmatch(piece) or not piece.strip():
            output_parts.append(piece)
            continue

        segments = split_segments(piece) or [piece.strip()]
        start_index = len(flat_segments)
        flat_segments.extend(segments)
        end_index = len(flat_segments)
        output_parts.append(None)
        segment_groups.append((len(output_parts) - 1, start_index, end_index))

    translated_segments = translate_segments(model_service, flat_segments, direction, protected_map, batch_size)
    for output_index, start_index, end_index in segment_groups:
        output_parts[output_index] = " ".join(translated_segments[start_index:end_index])

    return "".join(part or "" for part in output_parts)
