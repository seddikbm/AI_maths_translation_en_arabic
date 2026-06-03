from __future__ import annotations

import re


LATEX_PATTERN = re.compile(
    r"(\$\$.*?\$\$|\$.*?\$|\\\(.+?\\\)|\\\[.+?\\\]|<math.*?>.*?</math>)",
    re.DOTALL,
)
MATH_SYMBOLS = r"=+\-\u2212\u00d7*/^_\u2207\u2202\u2211\u222b\u221a\u2264\u2265<>\u2032'\u00b2\u00b3\u00b9"
GREEK_RANGE = r"\u0370-\u03ff"
SUPERSCRIPT_RANGE = r"\u2070-\u209f"
MATH_CHARS = re.compile(f"[{MATH_SYMBOLS}{GREEK_RANGE}{SUPERSCRIPT_RANGE}]")
ARABIC_CHARS = re.compile(r"[\u0600-\u06ff]")
LONG_WORDS = re.compile(r"[A-Za-z]{3,}|[\u0600-\u06ff]{3,}")
MATH_TOKEN_CHARS = rf"A-Za-z0-9{GREEK_RANGE}{SUPERSCRIPT_RANGE}\(\)\[\]\{{\}}\.,{MATH_SYMBOLS}"
MATH_OPERATORS = rf"[=+\-\u2212\u00d7*/^_\u2207\u2202\u2211\u222b\u221a\u2264\u2265<>]"
INLINE_EQUATION = re.compile(
    rf"(?<![A-Za-z0-9])([{MATH_TOKEN_CHARS}]+(?:\s*{MATH_OPERATORS}\s*[{MATH_TOKEN_CHARS}]+)+)"
)
INLINE_OPTIMIZATION = re.compile(
    rf"(?<![A-Za-z0-9])("
    rf"(?:arg\s*)?(?:min|max)\s*[{GREEK_RANGE}][A-Za-z0-9]*"
    rf"(?:\s*[A-Za-z]\s*[\u2032']?\s*\([^()\n]*\))?"
    rf")"
)
INLINE_MATH_ATOM = re.compile(
    rf"(?<![A-Za-z0-9])("
    rf"(?:[A-Za-z]\s*[\u2032']?\s*\([^()\n]*[{GREEK_RANGE}0-9][^()\n]*\))|"
    rf"(?:\u2207\s*[A-Za-z]?\([^()\n]*\))|"
    rf"(?:[{GREEK_RANGE}][A-Za-z0-9]*)|"
    rf"(?:\d+\.\d+)"
    rf")(?![A-Za-z0-9])"
)
PLACEHOLDER_PATTERN = re.compile(r"(<MATH_\d+>)")


def replace_latex(text: str) -> tuple[str, dict[str, str]]:
    mapping: dict[str, str] = {}

    def _repl(match: re.Match[str]) -> str:
        return _spaced_placeholder(mapping, match.group(0))

    protected = LATEX_PATTERN.sub(_repl, text)
    protected_lines = []
    for line in protected.splitlines():
        stripped = line.strip()
        if _is_math_line(stripped, mapping):
            protected_lines.append(_add_placeholder(mapping, stripped))
        else:
            protected_lines.append(_protect_inline_math(line, mapping))
    return "\n".join(protected_lines), mapping


def restore_latex(text: str, mapping: dict[str, str]) -> str:
    restored = text
    for placeholder, original in mapping.items():
        restored = restored.replace(placeholder, f" {original} ")
    restored = re.sub(r"[ \t]{2,}", " ", restored)
    return re.sub(r"[ \t]+\n", "\n", restored).strip()


def _add_placeholder(mapping: dict[str, str], value: str) -> str:
    placeholder = f"<MATH_{len(mapping)}>"
    mapping[placeholder] = value
    return placeholder


def _spaced_placeholder(mapping: dict[str, str], value: str) -> str:
    return f" {_add_placeholder(mapping, value.strip())} "


def _is_math_line(line: str, mapping: dict[str, str]) -> bool:
    if len(line) < 2 or line in mapping:
        return False
    if "<MATH_" in line:
        return False
    if ARABIC_CHARS.search(line):
        return False
    if not MATH_CHARS.search(line):
        return False
    return len(LONG_WORDS.findall(line)) <= 2 and len(line) <= 140


def _protect_inline_math(line: str, mapping: dict[str, str]) -> str:
    def protect_piece(pattern: re.Pattern[str], value: str) -> str:
        parts: list[str] = []
        for piece in PLACEHOLDER_PATTERN.split(value):
            if not piece:
                continue
            if PLACEHOLDER_PATTERN.fullmatch(piece):
                parts.append(piece)
            else:
                parts.append(pattern.sub(lambda match: _spaced_placeholder(mapping, match.group(1)), piece))
        return "".join(parts)

    parts: list[str] = []
    for piece in PLACEHOLDER_PATTERN.split(line):
        if not piece:
            continue
        if PLACEHOLDER_PATTERN.fullmatch(piece):
            parts.append(piece)
            continue
        piece = protect_piece(INLINE_EQUATION, piece)
        piece = protect_piece(INLINE_OPTIMIZATION, piece)
        parts.append(protect_piece(INLINE_MATH_ATOM, piece))
    return "".join(parts)
