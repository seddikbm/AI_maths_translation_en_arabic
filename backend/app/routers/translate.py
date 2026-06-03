from __future__ import annotations

from fastapi import APIRouter

from ..schemas import TranslateRequest, TranslateResponse
from ..services.latex_handler import replace_latex, restore_latex
from ..services.model_service import get_model_service
from ..services.translation_segments import translate_text_preserving_breaks


router = APIRouter(tags=["translate"])


@router.post("/translate", response_model=TranslateResponse)
def translate_text(payload: TranslateRequest) -> TranslateResponse:
    model_service = get_model_service()
    prepared_text, latex_map = replace_latex(payload.text)
    translated = translate_text_preserving_breaks(model_service, prepared_text, payload.direction, latex_map)
    return TranslateResponse(
        direction=payload.direction,
        source_text=payload.text,
        translated_text=restore_latex(translated, latex_map),
        backend=model_service.describe_backend(),
    )
