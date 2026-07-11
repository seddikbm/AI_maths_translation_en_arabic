from __future__ import annotations

from dataclasses import dataclass
<<<<<<< HEAD
from io import BytesIO

import fitz
from PIL import Image
=======
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import re
from typing import Any

import fitz
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
>>>>>>> codex/mathtrans-current-version

from ..config import get_settings
from ..utils.text_utils import normalize_whitespace


<<<<<<< HEAD
=======
OCR_HEADING_LINE = re.compile(r"^(?:(?:\d+|[IVXLCDM]+)[\.\)]\s+\S)", re.IGNORECASE)
ARABIC_CHARS = re.compile(r"[\u0600-\u06ff]")
RTL_TRAILING_NUMBERED_HEADING = re.compile(r"^[\.\)]\s*(?P<title>.*[\u0600-\u06ff].*?)(?P<number>\d+)$")
MATH_TOKEN_CHARS = r"A-Za-z0-9\u0370-\u03ff\u2070-\u209f\u00b2\u00b3\u00b9"
FORMULA_LINE = re.compile(r"[=<>]|\([^)]*\d[^)]*\)|[\u0370-\u03ff]")
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
@dataclass
class OCRResult:
    pages: list[str]
    backend: str


class OCRService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def extract_document(self, pdf_bytes: bytes, source_lang: str) -> OCRResult:
<<<<<<< HEAD
        text_pages = self._extract_embedded_text(pdf_bytes)
        if any(page.strip() for page in text_pages):
            return OCRResult(pages=text_pages, backend="embedded-text")

=======
        text_pages = self._extract_embedded_text(pdf_bytes, source_lang)
        if text_pages and all(page.strip() for page in text_pages):
            return OCRResult(pages=text_pages, backend="embedded-text")

        if any(page.strip() for page in text_pages):
            missing_indexes = [index for index, page in enumerate(text_pages) if not page.strip()]
            tess_lang = "ara" if source_lang == "ar" else "eng"
            ocr_pages = self._extract_with_tesseract(pdf_bytes, tess_lang, page_indexes=set(missing_indexes))
            merged_pages = list(text_pages)
            for page_index, page_text in ocr_pages.items():
                if page_index < len(merged_pages):
                    merged_pages[page_index] = page_text
            return OCRResult(pages=[page for page in merged_pages if page.strip()], backend="embedded-text+tesseract")

>>>>>>> codex/mathtrans-current-version
        if source_lang == "en":
            nougat_pages = self._extract_with_nougat(pdf_bytes)
            if nougat_pages:
                return OCRResult(pages=nougat_pages, backend="nougat")

        tess_lang = "ara" if source_lang == "ar" else "eng"
<<<<<<< HEAD
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
=======
        return OCRResult(pages=list(self._extract_with_tesseract(pdf_bytes, tess_lang).values()), backend="tesseract")

    def _extract_embedded_text(self, pdf_bytes: bytes, source_lang: str = "en") -> list[str]:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            pages: list[str] = []
            for page_index, page in enumerate(document):
                if page_index >= self.settings.max_pdf_pages:
                    break
                pages.append(self._clean_embedded_text(page.get_text("text", sort=source_lang != "ar")))
            return pages
        finally:
            document.close()

    def _clean_embedded_text(self, text: str) -> str:
        lines: list[str] = []
        seen_content = False

        def append_blank() -> None:
            if lines and lines[-1] != "":
                lines.append("")

        for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = normalize_whitespace(raw_line).strip(" |\u00a2\u2022\u00b7'\"`")
            line = self._repair_rtl_extracted_line(line)
            if line.isdigit():
                continue
            if line and (not seen_content or OCR_HEADING_LINE.match(line) or _is_unnumbered_heading(line)):
                append_blank()
                lines.append(line)
                lines.append("")
                seen_content = True
                continue
            if line:
                lines.append(line)
                seen_content = True
            elif lines and lines[-1] != "":
                lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    def _repair_rtl_extracted_line(self, line: str) -> str:
        if not line or not ARABIC_CHARS.search(line):
            return line

        heading_match = RTL_TRAILING_NUMBERED_HEADING.match(line)
        if heading_match:
            title = heading_match.group("title").strip()
            number = heading_match.group("number")
            if len(title.split()) <= 5:
                return f"{number}. {title}"

        if line[0] in ":؛،." and len(line) > 1:
            line = f"{line[1:].strip()}{line[0]}"

        line = re.sub(rf"([\u0600-\u06ff])([{MATH_TOKEN_CHARS}])", r"\1 \2", line)
        line = re.sub(rf"([{MATH_TOKEN_CHARS}])([\u0600-\u06ff])", r"\1 \2", line)
        return line

    def _extract_with_nougat(self, pdf_bytes: bytes) -> list[str]:
        model_ref = self._resolve_nougat_model_ref()
        if not model_ref:
            return []
        try:
>>>>>>> codex/mathtrans-current-version
            import torch
        except ImportError:
            return []

<<<<<<< HEAD
        processor = NougatProcessor.from_pretrained(self.settings.nougat_model_name)
        model = VisionEncoderDecoderModel.from_pretrained(self.settings.nougat_model_name)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
=======
        try:
            device_name = self.settings.device or ("cuda" if torch.cuda.is_available() else "cpu")
            processor, model, device = _load_nougat_model(model_ref, device_name)
        except Exception:
            return []

>>>>>>> codex/mathtrans-current-version
        pages: list[str] = []
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_index, page in enumerate(document):
                if page_index >= self.settings.max_pdf_pages:
                    break
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
<<<<<<< HEAD
                pixel_values = processor(images=image, return_tensors="pt").pixel_values.to(device)
                generated = model.generate(pixel_values, max_length=2048)
                text = processor.batch_decode(generated, skip_special_tokens=True)[0]
                normalized = normalize_whitespace(text)
=======
                try:
                    pixel_values = processor(images=image, return_tensors="pt").pixel_values.to(device)
                    with torch.inference_mode():
                        generated = model.generate(pixel_values, max_new_tokens=2048)
                    text = processor.batch_decode(generated, skip_special_tokens=True)[0]
                except Exception:
                    return []
                normalized = self._clean_nougat_text(text)
>>>>>>> codex/mathtrans-current-version
                if normalized:
                    pages.append(normalized)
        finally:
            document.close()
        return pages

<<<<<<< HEAD
    def _extract_with_tesseract(self, pdf_bytes: bytes, language: str) -> list[str]:
=======
    def _resolve_nougat_model_ref(self) -> str | None:
        model_name = self.settings.nougat_model_name
        if not model_name:
            return None

        model_path = Path(model_name)
        if model_path.is_absolute():
            return str(model_path) if model_path.exists() else None

        if "/" in model_name or "\\" in model_name:
            for candidate in self._model_path_candidates(model_path):
                if candidate.exists():
                    return str(candidate)
            return None

        return model_name

    def _model_path_candidates(self, model_path: Path) -> list[Path]:
        project_root = Path(__file__).resolve().parents[3]
        return [
            (Path.cwd() / model_path).resolve(),
            (project_root / model_path).resolve(),
            (project_root.parent / model_path).resolve(),
        ]

    def _clean_nougat_text(self, text: str) -> str:
        lines: list[str] = []
        for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw_line.strip()
            if line:
                lines.append(line)
            elif lines and lines[-1] != "":
                lines.append("")
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)

    def _extract_with_tesseract(
        self,
        pdf_bytes: bytes,
        language: str,
        page_indexes: set[int] | None = None,
    ) -> dict[int, str]:
>>>>>>> codex/mathtrans-current-version
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError("pytesseract is required for OCR fallback.") from exc

<<<<<<< HEAD
        pages: list[str] = []
=======
        pages: dict[int, str] = {}
>>>>>>> codex/mathtrans-current-version
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            for page_index, page in enumerate(document):
                if page_index >= self.settings.max_pdf_pages:
                    break
<<<<<<< HEAD
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                text = pytesseract.image_to_string(image, lang=language)
                normalized = normalize_whitespace(text)
                if normalized:
                    pages.append(normalized)
        finally:
            document.close()
        return pages
=======
                if page_indexes is not None and page_index not in page_indexes:
                    continue
                scale = 4 if language == "ara" else 2
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
                image = self._prepare_tesseract_image(image, language)
                text = pytesseract.image_to_string(image, lang=language, config=self._tesseract_config(language))
                if language == "ara":
                    text = self._drop_arabic_ocr_noise(text)
                normalized = self._clean_embedded_text(text)
                if normalized:
                    pages[page_index] = normalized
        finally:
            document.close()
        return pages

    def _prepare_tesseract_image(self, image: Image.Image, language: str) -> Image.Image:
        if language != "ara":
            return image

        image = self._crop_bright_document_area(image)
        gray = ImageOps.grayscale(image)
        gray = ImageEnhance.Contrast(gray).enhance(1.8)
        return gray.filter(ImageFilter.SHARPEN)

    def _crop_bright_document_area(self, image: Image.Image) -> Image.Image:
        gray = ImageOps.grayscale(image)
        pixels = np.asarray(gray)
        mask = pixels > 80
        rows = np.where(mask.any(axis=1))[0]
        cols = np.where(mask.any(axis=0))[0]
        if rows.size == 0 or cols.size == 0:
            return image

        y0, y1 = int(rows[0]), int(rows[-1])
        x0, x1 = int(cols[0]), int(cols[-1])
        pad = max(10, min(image.size) // 100)
        return image.crop(
            (
                max(0, x0 - pad),
                max(0, y0 - pad),
                min(image.width, x1 + pad),
                min(image.height, y1 + pad),
            )
        )

    def _tesseract_config(self, language: str) -> str:
        if language == "ara":
            return "--oem 1 --psm 4 -c preserve_interword_spaces=1"
        return "--oem 1 --psm 6"

    def _drop_arabic_ocr_noise(self, text: str) -> str:
        lines = []
        for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            stripped = line.strip()
            if not stripped or not self._is_arabic_ocr_noise_line(stripped):
                lines.append(line)
        return "\n".join(lines)

    def _is_arabic_ocr_noise_line(self, line: str) -> bool:
        compact = normalize_whitespace(line)
        if not compact:
            return False
        arabic_count = len(ARABIC_CHARS.findall(compact))
        if FORMULA_LINE.search(compact):
            return False
        if arabic_count == 0:
            return True
        if arabic_count < 3 and len(compact) > 8:
            return True
        return arabic_count / max(len(compact), 1) < 0.12 and len(compact) > 18


@lru_cache(maxsize=1)
def _load_nougat_model(model_ref: str, device_name: str) -> tuple[Any, Any, Any]:
    import torch
    from transformers import NougatProcessor, VisionEncoderDecoderModel

    device = torch.device(device_name)
    processor = NougatProcessor.from_pretrained(model_ref)
    model = VisionEncoderDecoderModel.from_pretrained(model_ref)
    model.to(device)
    model.eval()
    return processor, model, device


def _is_unnumbered_heading(line: str) -> bool:
    normalized = re.sub(r"^[\s:;.,\-\u060c\u061b]+|[\s:;.,\-\u060c\u061b]+$", "", line).casefold()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized in UNNUMBERED_HEADING_LABELS
>>>>>>> codex/mathtrans-current-version
