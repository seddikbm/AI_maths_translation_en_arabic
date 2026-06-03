from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

os.environ["TRANSLATION_BACKEND"] = "mock"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app
from app.routers.document import _filter_ocr_noise, _split_page_blocks
from app.services.latex_handler import replace_latex
from app.services.ocr_service import OCRService
from app.services.pdf_builder import PDFBuilder
from app.services.translation_segments import translate_segments
from app.schemas import TranslationDirection


client = TestClient(app)


def _make_pdf(text: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.save()
    return buffer.getvalue()


def test_health(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_translate_text(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.post(
        "/api/translate",
        json={"text": "If $x^2$ is positive.", "direction": "en2ar"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "mock"
    assert "<MATH_0>" not in payload["translated_text"]
    assert "$x^2$" in payload["translated_text"]


def test_translate_text_splits_paragraphs(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.post(
        "/api/translate",
        json={
            "text": "First paragraph has $x^2$.\n\nSecond paragraph has $y$.",
            "direction": "en2ar",
        },
    )
    assert response.status_code == 200
    translated = response.json()["translated_text"]
    assert translated.count("[mock Arabic]") >= 2
    assert "\n\n" in translated
    assert "$x^2$" in translated
    assert "$y$" in translated


def test_translate_text_preserves_line_breaks(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.post(
        "/api/translate",
        json={
            "text": "First line.\nSecond line.\n\nFourth line.",
            "direction": "en2ar",
        },
    )
    assert response.status_code == 200
    translated = response.json()["translated_text"]
    assert translated.count("\n") == 3
    assert "[mock Arabic] First line.\n[mock Arabic] Second line.\n\n[mock Arabic] Fourth line." == translated


def test_translate_text_preserves_math_lines(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    formula = "\u03b8new = \u03b8old \u2212 \u03b1\u2207J(\u03b8)"
    response = client.post(
        "/api/translate",
        json={
            "text": f"The update rule is:\n\n{formula}\n\nRepeat until convergence.",
            "direction": "en2ar",
        },
    )
    assert response.status_code == 200
    translated = response.json()["translated_text"]
    assert formula in translated
    assert f"[mock Arabic] {formula}" not in translated


def test_replace_latex_protects_arabic_inline_math() -> None:
    text = "\u0625\u0630\u0627 \u0643\u0627\u0646\u03b8old = 4 \u0648\u03b1 = 0.1\u060c \u0641\u0625\u0646:"
    protected, mapping = replace_latex(text)
    assert "\u03b8old = 4" in mapping.values()
    assert "\u03b1 = 0.1" in mapping.values()
    assert "\u03b8old = 4" not in protected
    assert "\u03b1 = 0.1" not in protected


def test_translate_segments_keeps_inline_math_placeholders() -> None:
    class FakeModelService:
        def translate_texts(self, texts: list[str], direction: TranslationDirection) -> list[str]:
            return [f"T({text})" for text in texts]

    result = translate_segments(
        FakeModelService(),
        ["\u0625\u0630\u0627 \u0643\u0627\u0646 <MATH_0> \u0641\u0625\u0646"],
        TranslationDirection.ar2en,
        {"<MATH_0>": "\u03b8old = 4"},
    )
    assert result == ["T(\u0625\u0630\u0627 \u0643\u0627\u0646 <MATH_0> \u0641\u0625\u0646)"]


def test_translate_segments_falls_back_if_placeholder_is_dropped() -> None:
    class DroppingModelService:
        def translate_texts(self, texts: list[str], direction: TranslationDirection) -> list[str]:
            return ["broken" if "<MATH_0>" in text else f"T({text})" for text in texts]

    result = translate_segments(
        DroppingModelService(),
        ["\u0625\u0630\u0627 \u0643\u0627\u0646 <MATH_0> \u0641\u0625\u0646"],
        TranslationDirection.ar2en,
        {"<MATH_0>": "\u03b8old = 4"},
    )
    assert result == ["T(\u0625\u0630\u0627 \u0643\u0627\u0646 )<MATH_0>T( \u0641\u0625\u0646)"]


def test_pdf_builder_detects_section_headings() -> None:
    builder = PDFBuilder()
    assert builder._is_section_heading("1. \u0645\u0642\u062f\u0645\u0629")
    assert builder._is_section_heading("II - Background")
    assert builder._is_section_heading("\u0627\u0644\u0646\u062a\u064a\u062c\u0629 4")
    assert builder._is_section_heading("Summary")
    assert builder._is_section_heading("The summary")
    assert builder._is_section_heading("\u0627\u0644\u0645\u0644\u062e\u0635")
    assert not builder._is_section_heading("\u03b8new = \u03b8old \u2212 \u03b1\u2207J(\u03b8)")
    assert not builder._is_section_heading("This is a normal paragraph with enough words to be body text.")


def test_ocr_cleanup_preserves_line_breaks() -> None:
    text = "Title\n\nFirst OCR line\nSecond OCR line\n\n1\n\nNext section"
    cleaned = OCRService()._clean_embedded_text(text)
    assert cleaned == "Title\n\nFirst OCR line\nSecond OCR line\n\nNext section"


def test_ocr_cleanup_splits_heading_lines() -> None:
    text = "Title\nAbstract\nText body.\n1. Introduction\nMore body."
    cleaned = OCRService()._clean_embedded_text(text)
    assert cleaned == "Title\n\nAbstract\n\nText body.\n\n1. Introduction\n\nMore body."


def test_ocr_cleanup_splits_summary_headings() -> None:
    text = "Title\nSummary\nText body.\n\u0627\u0644\u0645\u0644\u062e\u0635\n\u0646\u0635 \u0639\u0631\u0628\u064a."
    cleaned = OCRService()._clean_embedded_text(text)
    assert cleaned == "Title\n\nSummary\n\nText body.\n\n\u0627\u0644\u0645\u0644\u062e\u0635\n\n\u0646\u0635 \u0639\u0631\u0628\u064a."


def test_ocr_cleanup_strips_edge_noise() -> None:
    text = "| Probability helps AI.\n¢ errors, and evaluate models."
    cleaned = OCRService()._clean_embedded_text(text)
    assert cleaned == "Probability helps AI.\n\nerrors, and evaluate models."


def test_ocr_cleanup_repairs_arabic_numbered_heading() -> None:
    text = "\u0627\u0644\u0645\u0644\u062e\u0635\n. \u0627\u0644\u0645\u0642\u062f\u0645\u06291"
    cleaned = OCRService()._clean_embedded_text(text)
    assert cleaned == "\u0627\u0644\u0645\u0644\u062e\u0635\n\n1. \u0627\u0644\u0645\u0642\u062f\u0645\u0629"


def test_arabic_ocr_noise_line_filter() -> None:
    service = OCRService()
    assert service._is_arabic_ocr_noise_line("| 5-7 -- 11")
    assert service._is_arabic_ocr_noise_line("ab 12 ++")
    assert not service._is_arabic_ocr_noise_line("\u0627\u0644\u0627\u0646\u062d\u062f\u0627\u0631 \u0627\u0644\u062a\u062f\u0631\u062c\u064a \u0637\u0631\u064a\u0642\u0629 \u0631\u064a\u0627\u0636\u064a\u0629")
    assert not service._is_arabic_ocr_noise_line("\u03b8new = \u03b8old - \u03b1")


def test_arabic_tesseract_config_uses_layout_mode() -> None:
    assert OCRService()._tesseract_config("ara") == "--oem 1 --psm 4 -c preserve_interword_spaces=1"


def test_nougat_resolver_skips_missing_local_path() -> None:
    service = OCRService()
    service.settings.nougat_model_name = "/definitely/missing/nougat"
    assert service._resolve_nougat_model_ref() is None


def test_nougat_cleanup_preserves_markdown_breaks() -> None:
    text = "# Title\n\nParagraph one.\n\n\nParagraph two."
    cleaned = OCRService()._clean_nougat_text(text)
    assert cleaned == "# Title\n\nParagraph one.\n\nParagraph two."


def test_tesseract_noise_filter_keeps_headings_and_math() -> None:
    segments = [
        "Abstract",
        "1. Introduction",
        "x = (x1, x2, x3)",
        "Weert allt ids Sy",
        "This is a valid sentence.",
    ]
    assert _filter_ocr_noise(segments, "tesseract") == [
        "Abstract",
        "1. Introduction",
        "x = (x1, x2, x3)",
        "This is a valid sentence.",
    ]
    assert _filter_ocr_noise(["Weert allt ids Sy"], "embedded-text") == ["Weert allt ids Sy"]


def test_split_page_blocks_preserves_formula_lines() -> None:
    page = "Intro line\nx = y + 1\n\n1. Heading\nBody line"
    assert _split_page_blocks(page) == ["Intro line", "x = y + 1", "1. Heading Body line"]


def test_split_page_blocks_keeps_unnumbered_headings_separate() -> None:
    page = "Summary\nThis is body text.\n\n\u0627\u0644\u0645\u0644\u062e\u0635\n\u0647\u0630\u0627 \u0646\u0635."
    assert _split_page_blocks(page) == [
        "Summary",
        "This is body text.",
        "\u0627\u0644\u0645\u0644\u062e\u0635",
        "\u0647\u0630\u0627 \u0646\u0635.",
    ]


def test_translate_document(monkeypatch) -> None:
    monkeypatch.setenv("TRANSLATION_BACKEND", "mock")
    response = client.post(
        "/api/translate/document",
        data={"direction": "en2ar"},
        files={"file": ("sample.pdf", _make_pdf("If x > 0 then f(x) = x."), "application/pdf")},
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
