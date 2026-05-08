from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TranslationDirection(str, Enum):
    en2ar = "en2ar"
    ar2en = "ar2en"

    @property
    def source_lang(self) -> str:
        return "en" if self is TranslationDirection.en2ar else "ar"

    @property
    def target_lang(self) -> str:
        return "ar" if self is TranslationDirection.en2ar else "en"

    @property
    def prompt_prefix(self) -> str:
        return f"<{self.value}>"


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    direction: TranslationDirection


class TranslateResponse(BaseModel):
    direction: TranslationDirection
    source_text: str
    translated_text: str
    backend: str


class HealthResponse(BaseModel):
    status: str
    backend: str
