from __future__ import annotations

import html
import re
from io import BytesIO
from pathlib import Path

from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from ..config import get_settings
from ..utils.text_utils import shape_arabic_text


MATH_SYMBOLS = re.compile(r"[=+\u2212\u00d7*/^_\u2207\u2202\u2211\u222b\u221a\u2264\u2265<>]")
SECTION_MARKER = re.compile(
    r"(^\s*(?:\d+|[IVXLCDM]+|[ivxlcdm]+|[\u0660-\u0669]+)\s*[\.\-:)]|[\.\-:]?\s*(?:\d+|[IVXLCDM]+|[ivxlcdm]+|[\u0660-\u0669]+)\s*$)"
)
UNNUMBERED_SECTION_LABELS = {
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


class PDFBuilder:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._registered_arabic_font = False
        self._registered_arabic_bold_font = False
        self._registered_unicode_font = False
        self._registered_unicode_bold_font = False

    def _arabic_font_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self.settings.arabic_font_path:
            candidates.append(self.settings.arabic_font_path)
        candidates.extend(
            [
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
                Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
                Path("C:/Windows/Fonts/arial.ttf"),
                Path("C:/Windows/Fonts/tahoma.ttf"),
                Path(__file__).resolve().parents[2] / "fonts" / "NotoSansArabic-Regular.ttf",
            ]
        )
        return candidates

    def _arabic_bold_font_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self.settings.arabic_font_path:
            font_path = self.settings.arabic_font_path
            candidates.append(font_path.with_name(f"{font_path.stem}-Bold{font_path.suffix}"))
        candidates.extend(
            [
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"),
                Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf"),
                Path("C:/Windows/Fonts/arialbd.ttf"),
                Path("C:/Windows/Fonts/tahomabd.ttf"),
            ]
        )
        return candidates

    def _unicode_font_candidates(self) -> list[Path]:
        return [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/tahoma.ttf"),
        ]

    def _unicode_bold_font_candidates(self) -> list[Path]:
        return [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
            Path("C:/Windows/Fonts/tahomabd.ttf"),
        ]

    def _resolve_font_name(self, target_language: str, bold: bool = False) -> str:
        if target_language != "ar":
            candidates = self._unicode_bold_font_candidates() if bold else self._unicode_font_candidates()
            font_path = next((candidate for candidate in candidates if candidate.exists()), None)
            if font_path is None:
                return "Helvetica-Bold" if bold else "Helvetica"
            font_name = "MathTransUnicodeBold" if bold else "MathTransUnicode"
            registered_attr = "_registered_unicode_bold_font" if bold else "_registered_unicode_font"
            if not getattr(self, registered_attr):
                pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                setattr(self, registered_attr, True)
            return font_name
        if bold:
            bold_font_path = next((candidate for candidate in self._arabic_bold_font_candidates() if candidate.exists()), None)
            if bold_font_path is not None:
                font_name = "MathTransArabicBold"
                if not self._registered_arabic_bold_font:
                    pdfmetrics.registerFont(TTFont(font_name, str(bold_font_path)))
                    self._registered_arabic_bold_font = True
                return font_name
        font_path = next((candidate for candidate in self._arabic_font_candidates() if candidate.exists()), None)
        if font_path is None:
            raise RuntimeError("Arabic font is not configured. Set ARABIC_FONT_PATH to a valid .ttf file.")
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
        return self.build_document_pages([translated_segments], target_language, source_filename)

    def build_document_pages(
        self,
        translated_pages: list[list[str]],
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
            fontSize=10 if target_language == "ar" else 11,
            leading=15 if target_language == "ar" else 17,
            alignment=alignment,
        )
        title_style = ParagraphStyle(
            "MathTransTitle",
            parent=body_style,
            fontName=self._resolve_font_name(target_language, bold=True),
            fontSize=17 if target_language == "ar" else 16,
            leading=24 if target_language == "ar" else 22,
            spaceAfter=8,
        )
        heading_style = ParagraphStyle(
            "MathTransHeading",
            parent=body_style,
            fontName=self._resolve_font_name(target_language, bold=True),
            fontSize=13 if target_language == "ar" else 13,
            leading=19 if target_language == "ar" else 18,
            spaceBefore=6,
            spaceAfter=4,
        )
        story = []
        non_empty_pages = [page for page in translated_pages if page]
        is_first_segment = True
        for page_index, page_segments in enumerate(non_empty_pages):
            for segment in page_segments:
                segment_style = self._style_for_segment(segment, is_first_segment, title_style, heading_style, body_style)
                content = shape_arabic_text(segment) if target_language == "ar" else segment
                safe_content = html.escape(content).replace("\n", "<br/>")
                story.append(Paragraph(safe_content, segment_style))
                story.append(Spacer(1, 10))
                is_first_segment = False
            if page_index < len(non_empty_pages) - 1:
                story.append(PageBreak())
        document.build(story)
        return buffer.getvalue()

    def _style_for_segment(
        self,
        segment: str,
        is_first_segment: bool,
        title_style: ParagraphStyle,
        heading_style: ParagraphStyle,
        body_style: ParagraphStyle,
    ) -> ParagraphStyle:
        if is_first_segment:
            return title_style
        return heading_style if self._is_section_heading(segment) else body_style

    def _is_section_heading(self, segment: str) -> bool:
        compact = " ".join(segment.split())
        if not compact or len(compact) > 90:
            return False
        if MATH_SYMBOLS.search(compact):
            return False
        return bool(SECTION_MARKER.search(compact)) or self._is_unnumbered_section_label(compact)

    def _is_unnumbered_section_label(self, compact: str) -> bool:
        normalized = re.sub(r"^[\s:;.,\-\u060c\u061b]+|[\s:;.,\-\u060c\u061b]+$", "", compact).casefold()
        normalized = re.sub(r"\s+", " ", normalized)
        if normalized.startswith("the "):
            normalized = normalized[4:]
        return normalized in UNNUMBERED_SECTION_LABELS
