from __future__ import annotations

import html
from io import BytesIO

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from ..config import get_settings
from ..utils.text_utils import shape_arabic_text


class PDFBuilder:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._registered_arabic_font = False

    def _resolve_font_name(self, target_language: str) -> str:
        if target_language != "ar" or not self.settings.arabic_font_path:
            return "Helvetica"
        font_path = self.settings.arabic_font_path
        if not font_path.exists():
            return "Helvetica"
        font_name = "MathTransArabic"
        if not self._registered_arabic_font:
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            self._registered_arabic_font = True
        return font_name

    def build_document(
        self,
        translated_segments: list[str],
        target_language: str,
        source_filename: str,
    ) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=48,
            rightMargin=48,
            topMargin=48,
            bottomMargin=48,
            title=f"Translated {source_filename}",
        )
        styles = getSampleStyleSheet()
        alignment = TA_RIGHT if target_language == "ar" else TA_LEFT
        body_style = ParagraphStyle(
            "MathTransBody",
            parent=styles["BodyText"],
            fontName=self._resolve_font_name(target_language),
            fontSize=11,
            leading=17,
            alignment=alignment,
        )
        story = []
        for segment in translated_segments:
            content = shape_arabic_text(segment) if target_language == "ar" else segment
            safe_content = html.escape(content).replace("\n", "<br/>")
            story.append(Paragraph(safe_content, body_style))
            story.append(Spacer(1, 10))
        document.build(story)
        return buffer.getvalue()
