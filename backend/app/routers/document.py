from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..schemas import TranslationDirection
from ..services.latex_handler import replace_latex, restore_latex
from ..services.model_service import get_model_service
from ..services.ocr_service import OCRService
from ..services.pdf_builder import PDFBuilder
from ..utils.text_utils import split_segments


router = APIRouter(tags=["document"])


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
        target_language=direction.target_lang,
        source_filename=file.filename,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{file.filename.rsplit(".", 1)[0]}_{direction.value}.pdf"',
        "X-Translation-Backend": model_service.describe_backend(),
        "X-OCR-Backend": ocr_result.backend,
    }
    return StreamingResponse(BytesIO(output_bytes), media_type="application/pdf", headers=headers)
