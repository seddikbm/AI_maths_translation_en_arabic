from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config import get_settings
from ..schemas import TranslationDirection


LANG_MAP = {"en": "eng_Latn", "ar": "arb_Arab"}


class ModelService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._tokenizer: Any = None
        self._model: Any = None
        self._device: Any = None
        self._openai_client: Any = None
        self._active_backend: str | None = None

    def describe_backend(self) -> str:
        return self._active_backend or self._resolve_backend()

    def translate_texts(self, texts: list[str], direction: TranslationDirection) -> list[str]:
        backend = self._resolve_backend()
        if backend == "mock":
            self._active_backend = "mock"
            return [self._mock_translate(text, direction) for text in texts]
        if backend == "openai":
            self._active_backend = "openai"
            return self._translate_openai(texts, direction)
        if backend in {"local", "auto"}:
            self._active_backend = "local"
            return self._translate_local(texts, direction)
        raise HTTPException(status_code=500, detail=f"Unsupported backend: {backend}")

    def _resolve_backend(self) -> str:
        return self.settings.translation_backend.lower().strip()

    def _translate_local(self, texts: list[str], direction: TranslationDirection) -> list[str]:
        self._ensure_local_model()
        tokenizer = self._tokenizer
        model = self._model
        device = self._device
        tokenizer.src_lang = LANG_MAP[direction.source_lang]
        prefixed = [f"{direction.prompt_prefix} {text}".strip() for text in texts]
        encoded = tokenizer(
            prefixed,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        encoded = {key: value.to(device) for key, value in encoded.items()}
        generated = model.generate(
            **encoded,
            max_length=512,
            forced_bos_token_id=self._language_token_id(tokenizer, LANG_MAP[direction.target_lang]),
            no_repeat_ngram_size=4,
            repetition_penalty=1.12,
        )
        return tokenizer.batch_decode(generated, skip_special_tokens=True)

    def _language_token_id(self, tokenizer: Any, lang_code: str) -> int:
        get_lang_id = getattr(tokenizer, "get_lang_id", None)
        if callable(get_lang_id):
            try:
                return int(get_lang_id(lang_code))
            except (KeyError, TypeError, ValueError):
                pass

        convert_tokens_to_ids = getattr(tokenizer, "convert_tokens_to_ids", None)
        if callable(convert_tokens_to_ids):
            token_id = convert_tokens_to_ids(lang_code)
            if token_id is not None and token_id != getattr(tokenizer, "unk_token_id", None):
                return int(token_id)

        added_tokens = getattr(tokenizer, "added_tokens_decoder", {})
        for added_token_id, added_token in added_tokens.items():
            if getattr(added_token, "content", None) == lang_code:
                return int(added_token_id)

        lang_code_to_id = getattr(tokenizer, "lang_code_to_id", None)
        if isinstance(lang_code_to_id, dict) and lang_code in lang_code_to_id:
            return int(lang_code_to_id[lang_code])

        raise HTTPException(status_code=500, detail=f"Tokenizer does not contain language token: {lang_code}")

    def _translate_openai(self, texts: list[str], direction: TranslationDirection) -> list[str]:
        client = self._get_openai_client()
        source_name = "English" if direction.source_lang == "en" else "Arabic"
        target_name = "Arabic" if direction.target_lang == "ar" else "English"
        completion = client.chat.completions.create(
            model=self.settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Translate {source_name} math text into {target_name}. "
                        "Preserve placeholders such as <MATH_0> exactly. "
                        "Return strict JSON with a single key named translations."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps({"texts": texts}, ensure_ascii=False),
                },
            ],
        )
        content = completion.choices[0].message.content or "{}"
        payload = json.loads(content)
        translations = payload.get("translations", [])
        if len(translations) != len(texts):
            raise HTTPException(status_code=502, detail="OpenAI translation returned an unexpected response shape.")
        return [str(item) for item in translations]

    def _mock_translate(self, text: str, direction: TranslationDirection) -> str:
        label = "Arabic" if direction.target_lang == "ar" else "English"
        return f"[mock {label}] {text}"

    def _ensure_local_model(self) -> None:
        if self._tokenizer is not None and self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:
            raise HTTPException(status_code=500, detail="Transformers dependencies are not installed.") from exc

        model_ref = self._resolve_model_ref()
        self._device = torch.device(self.settings.device or ("cuda" if torch.cuda.is_available() else "cpu"))
        torch_dtype = torch.float16 if self._device.type == "cuda" else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(model_ref)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(model_ref, torch_dtype=torch_dtype)
        self._model.to(self._device)
        self._model.eval()

    def _resolve_model_ref(self) -> str:
        model_path = self.settings.model_path
        if model_path:
            for candidate in self._model_path_candidates(Path(model_path)):
                if candidate.exists():
                    return str(candidate)
            raise HTTPException(status_code=500, detail=f"Configured MODEL_PATH does not exist: {model_path}")
        if self.settings.model_name:
            return self.settings.model_name
        raise HTTPException(status_code=500, detail="No model path or model name configured.")

    def _model_path_candidates(self, model_path: Path) -> list[Path]:
        if model_path.is_absolute():
            return [model_path]

        project_root = Path(__file__).resolve().parents[3]
        candidates = [
            Path.cwd() / model_path,
            project_root / model_path,
            project_root.parent / model_path,
        ]
        unique_candidates: list[Path] = []
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved not in unique_candidates:
                unique_candidates.append(resolved)
        return unique_candidates

    def _get_openai_client(self) -> Any:
        if self._openai_client is None:
            if not self.settings.openai_api_key:
                raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not configured.")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise HTTPException(status_code=500, detail="OpenAI SDK is not installed.") from exc
            self._openai_client = OpenAI(api_key=self.settings.openai_api_key)
        return self._openai_client


@lru_cache(maxsize=1)
def get_model_service() -> ModelService:
    return ModelService()
