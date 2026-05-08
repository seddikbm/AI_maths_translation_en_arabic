from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import fitz
from PIL import Image

from ..config import get_settings
from ..utils.text_utils import normalize_whitespace


@dataclass
class OCRResult:
    pages: list[str]
    backend: str


class OCRService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def extract_document(self, pdf_bytes: bytes, source_lang: str) -> OCRResult:
        text_pages = self._extract_embedded_text(pdf_bytes)
        if any(page.strip() for page in text_pages):
            return OCRResult(pages=text_pages, backend="embedded-text")

        if source_lang == "en":
            nougat_pages = self._extract_with_nougat(pdf_bytes)
            if nougat_pages:
                return OCRResult(pages=nougat_pages, backend="nougat")

        tess_lang = "ara" if source_lang == "ar" else "eng"
        return OCRResult(pages=self._extract_with_tesseract(pdf_bytes, tess_lang), backend="tesseract")

    def _extract_embedded_text(self, pdf_bytes: bytes) -> list[str]:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            pages = [normalize_whitespace(page.get_text("text")) for page in document]
            return [page for page in pages if page]
        finally:
            document.close()

    def _extract_with_nougat(self, pdf_bytes: bytes) -> list[str]:
        if not self.settings.nougat_model_name:
            return []
        try:
            from transformers import NougatProcessor, VisionEncoderDecoderModel
            import torch
        except ImportError:
            return []

        processor = NougatProcessor.from_pretrained(self.settings.nougat_model_name)
        model = VisionEncoderDecoderModel.from_pretrained(self.settings.nougat_model_name)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        pages: list[str] = []
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_index, page in enumerate(document):
                if page_index >= self.settings.max_pdf_pages:
                    break
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                pixel_values = processor(images=image, return_tensors="pt").pixel_values.to(device)
                generated = model.generate(pixel_values, max_length=2048)
                text = processor.batch_decode(generated, skip_special_tokens=True)[0]
                normalized = normalize_whitespace(text)
                if normalized:
                    pages.append(normalized)
        finally:
            document.close()
        return pages

    def _extract_with_tesseract(self, pdf_bytes: bytes, language: str) -> list[str]:
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is required for OCR fallback.") from exc

        pages: list[str] = []
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_index, page in enumerate(document):
                if page_index >= self.settings.max_pdf_pages:
                    break
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                text = pytesseract.image_to_string(image, lang=language)
                normalized = normalize_whitespace(text)
                if normalized:
                    pages.append(normalized)
        finally:
            document.close()
        return pages
