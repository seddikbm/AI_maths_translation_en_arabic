from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MathTrans API"
    api_prefix: str = "/api"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    translation_backend: str = "local"
    model_name: str = "facebook/nllb-200-1.3B"
    model_path: Path | None = Path("models/phase2_final")
    device: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    nougat_model_name: str | None = None
    arabic_font_path: Path | None = None
    scratch_dir: Path = Path("tmp")
    max_pdf_pages: int = 25

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
