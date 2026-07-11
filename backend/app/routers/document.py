from __future__ import annotations

from io import BytesIO
<<<<<<< HEAD
=======
import re
>>>>>>> codex/mathtrans-current-version

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..schemas import TranslationDirection
from ..services.latex_handler import replace_latex, restore_latex
from ..services.model_service import get_model_service
from ..services.ocr_service import OCRService
from ..services.pdf_builder import PDFBuilder
<<<<<<< HEAD
from ..utils.text_utils import split_segments


router = APIRouter(tags=["document"])
=======
from ..services.translation_segments import translate_text_preserving_breaks


router = APIRouter(tags=["document"])
SHORT_WORDS = re.compile(r"[A-Za-z]{2,}")
IMPORTANT_MARKS = re.compile(r"[\d.!?:;=+\-\u2212\u00d7*/^_\u2207\u2202\u2211\u222b\u221a\u2264\u2265<>]")
ARABIC_CHARS = re.compile(r"[\u0600-\u06ff]")
DISPLAY_MATH_MARKS = re.compile(r"[=+\-\u2212\u00d7*/^_\u2207\u2202\u2211\u222b\u221a\u2264\u2265<>]|[\u0370-\u03ff]")
UNNUMBERED_HEADING_LABELS = {
    "abstract",
    "summary",
    "introduction",
    "background",
    "method",
    "methods",
    "methodology",
    "results",
    "discussion",
    "conclusion",
    "references",
    "appendix",
    "example",
    "proof",
    "\u0627\u0644\u0645\u0644\u062e\u0635",
    "\u0645\u0644\u062e\u0635",
    "\u0627\u0644\u062e\u0644\u0627\u0635\u0629",
    "\u062e\u0644\u0627\u0635\u0629",
    "\u0627\u0644\u0645\u0642\u062f\u0645\u0629",
    "\u0645\u0642\u062f\u0645\u0629",
    "\u0627\u0644\u062e\u0627\u062a\u0645\u0629",
    "\u062e\u0627\u062a\u0645\u0629",
    "\u0627\u0644\u0646\u062a\u0627\u0626\u062c",
    "\u0646\u062a\u0627\u0626\u062c",
    "\u0627\u0644\u0645\u0631\u0627\u062c\u0639",
    "\u0645\u0631\u0627\u062c\u0639",
    "\u0645\u062b\u0627\u0644",
    "\u0628\u0631\u0647\u0627\u0646",
}
>>>>>>> codex/mathtrans-current-version


@router.post("/translate/document")
async def translate_document(
    file: UploadFile = File(...),
    direction: TranslationDirection = Form(...),
) -> StreamingResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    pdf_bytes = await file.read()
    ocr_service = OCRService()
    ocr_result = ocr_service.extract_document(pdf_bytes, direction.source_lang)
<<<<<<< HEAD
    segments = split_segments("\n\n".join(ocr_result.pages))
    if not segments:
        raise HTTPException(status_code=422, detail="No translatable text was extracted from the PDF.")

    model_service = get_model_service()
    translated_segments: list[str] = []
    for segment in segments:
        prepared_text, latex_map = replace_latex(segment)
        translated = model_service.translate_texts([prepared_text], direction)[0]
        translated_segments.append(restore_latex(translated, latex_map))

    pdf_builder = PDFBuilder()
    output_bytes = pdf_builder.build_document(
        translated_segments,
=======
    page_segments = [
        _filter_ocr_noise(_split_page_blocks(page), ocr_result.backend)
        for page in ocr_result.pages
    ]
    if not any(page for page in page_segments):
        raise HTTPException(status_code=422, detail="No translatable text was extracted from the PDF.")

    model_service = get_model_service()
    translated_pages: list[list[str]] = []
    for segments in page_segments:
        translated_segments: list[str] = []
        for segment in segments:
            prepared_text, latex_map = replace_latex(segment)
            translated = translate_text_preserving_breaks(model_service, prepared_text, direction, latex_map)
            translated_segments.append(restore_latex(translated, latex_map))
        translated_pages.append(translated_segments)

    pdf_builder = PDFBuilder()
    output_bytes = pdf_builder.build_document_pages(
        translated_pages,
>>>>>>> codex/mathtrans-current-version
        target_language=direction.target_lang,
        source_filename=file.filename,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{file.filename.rsplit(".", 1)[0]}_{direction.value}.pdf"',
        "X-Translation-Backend": model_service.describe_backend(),
        "X-OCR-Backend": ocr_result.backend,
    }
    return StreamingResponse(BytesIO(output_bytes), media_type="application/pdf", headers=headers)
<<<<<<< HEAD
=======


def _split_page_blocks(page: str) -> list[str]:
    blocks: list[str] = []
    for block in re.split(r"\n{2,}", page):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        current: list[str] = []
        for line in lines:
            if _is_unnumbered_heading_line(line):
                if current:
                    blocks.append(" ".join(current))
                    current.clear()
                blocks.append(line)
            elif _is_display_math_line(line):
                if current:
                    blocks.append(" ".join(current))
                    current.clear()
                blocks.append(line)
            else:
                current.append(line)
        if current:
            blocks.append(" ".join(current))
    return blocks


def _is_display_math_line(line: str) -> bool:
    compact = " ".join(line.split())
    if not compact or ARABIC_CHARS.search(compact) or not DISPLAY_MATH_MARKS.search(compact):
        return False
    lowered = compact.lower()
    return "=" in compact or lowered.startswith(("min", "max", "argmin", "argmax"))


def _is_unnumbered_heading_line(line: str) -> bool:
    normalized = re.sub(r"^[\s:;.,\-\u060c\u061b]+|[\s:;.,\-\u060c\u061b]+$", "", line).casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in UNNUMBERED_HEADING_LABELS


def _filter_ocr_noise(segments: list[str], ocr_backend: str) -> list[str]:
    if "tesseract" not in ocr_backend:
        return segments
    return [segment for segment in segments if not _is_short_ocr_noise(segment)]


def _is_short_ocr_noise(segment: str) -> bool:
    compact = " ".join(segment.split())
    if len(compact) > 32 or IMPORTANT_MARKS.search(compact):
        return False
    words = SHORT_WORDS.findall(compact)
    if len(words) < 2:
        return False
    return all(len(word) <= 5 for word in words)
>>>>>>> codex/mathtrans-current-version
