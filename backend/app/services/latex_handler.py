from __future__ import annotations

import re


LATEX_PATTERN = re.compile(
    r"(\$\$.*?\$\$|\$.*?\$|\\\(.+?\\\)|\\\[.+?\\\]|<math.*?>.*?</math>)",
    re.DOTALL,
)


def replace_latex(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def _repl(match: re.Match[str]) -> str:
        placeholder = f"<MATH_{len(mapping)}>"
        mapping[placeholder] = match.group(0)
        return placeholder

    return LATEX_PATTERN.sub(_repl, text), mapping


def restore_latex(text: str, mapping: dict[str, str]) -> str:
    restored = text
    for placeholder, original in mapping.items():
        restored = restored.replace(placeholder, original)
    return restored
