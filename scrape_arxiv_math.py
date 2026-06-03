from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, TypedDict
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

import builtins

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:
    raise SystemExit("langgraph is required. Install dependencies from requirements.txt first.") from exc

load_dotenv()


def print(*args: Any, **kwargs: Any) -> None:
    safe_args = []
    for arg in args:
        if isinstance(arg, str):
            normalized = (
                arg.replace("âœ“", "[ok]")
                .replace("âœ—", "[skip]")
                .replace("âš ", "[warn]")
                .replace("⚠", "[warn]")
                .replace("✓", "[ok]")
                .replace("✗", "[skip]")
                .replace("â†’", "->")
                .replace("→", "->")
                .replace("â€¦", "...")
                .replace("…", "...")
                .replace("No HTML source worked", "HTML render unavailable")
            )
            safe_args.append(normalized.encode("ascii", "replace").decode("ascii"))
        else:
            safe_args.append(arg)
    builtins.print(*safe_args, **kwargs)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
AR5IV_URL = "https://ar5iv.labs.arxiv.org/html/{paper_id}"
ARXIV_HTML_URL = "https://arxiv.org/html/{paper_id}"   # official fallback (same ltx_ classes)
ARXIV_SOURCE_URL = "https://arxiv.org/e-print/{paper_id}"
ARXIV_MIN_REQUEST_INTERVAL = 3.0
ARXIV_MAX_RETRIES = 6
ARXIV_MAX_BACKOFF = 120.0
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+")
INLINE_LATEX_PATTERN = re.compile(r"(\$\$.*?\$\$|\$.*?\$|\\\(.+?\\\)|\\\[.+?\\\])", re.DOTALL)
DISPLAY_LATEX_ENV_PATTERN = re.compile(
    r"(\\begin\{(?:equation\*?|align\*?|aligned\*?|gather\*?|multline\*?|eqnarray\*?|displaymath)\}.*?"
    r"\\end\{(?:equation\*?|align\*?|aligned\*?|gather\*?|multline\*?|eqnarray\*?|displaymath)\})",
    re.DOTALL,
)
ENGLISH_PATTERN = re.compile(r"[A-Za-z]")
LATIN_WORD_PATTERN = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
ARABIC_WORD_PATTERN = re.compile(r"[\u0600-\u06FF]+")
PLACEHOLDER_PATTERN = re.compile(r"<(?:MATH_\d+|CITATION|REF)>")
LATEX_CITE_PATTERN = re.compile(r"\\cite\w*\*?(?:\[[^\]]*\]){0,2}\{.*?\}")
LATEX_REF_PATTERN = re.compile(r"\\(?:eqref|pageref|ref)\*?(?:\[[^\]]*\])?\{.*?\}")
EQUATION_LABEL_PATTERN = re.compile(r"\(\s*\d+(?:\.\d+)*\s*\)")
LATEX_COMMENT_PATTERN = re.compile(r"(?<!\\)%.*$")
RESIDUAL_LATEX_PATTERN = re.compile(
    r"\\(?:begin|end)\{[^}]*\}"
    r"|\\(?:emph|textbf|textit|textsl|textrm|textsf|texttt|mathrm|mathbf|mathit|mathcal|mathbb|mathsf)\{([^}]*)\}"
    r"|\\texorpdfstring\{([^}]*)\}\{[^}]*\}"
    r"|\\footnote\{[^}]*\}"
    r"|\\(?:item|bseq|eseq|notag|nonumber|displaystyle|textstyle|scriptstyle)\b"
    r"|\\(?:quad|qquad|hspace|vspace)(?:\{[^}]*\})?"
    r"|\\(?:left|right|big|Big|bigg|Bigg)[.()\[\]|]"
    r"|\\(?:label|tag)\*?\{[^}]*\}"
    r"|\\\\(?:\[\d+(?:pt|em|ex|mm|cm)\])?",
    re.DOTALL,
)
MATH_PLACEHOLDER_PATTERN = re.compile(r"<MATH_\d+>")
BODY_BLOCK_SELECTOR = (
    "p.ltx_p, li.ltx_item, div.ltx_caption, figcaption, "
    "table.ltx_equation, table.ltx_equationgroup"
)
SOURCE_MAIN_HINTS = {"main.tex", "ms.tex", "paper.tex", "article.tex"}

# ── CSS classes used by ar5iv for actual paper content ──────────────────────
# These are generated from LaTeX2HTML / latexml and represent real document
# sections, theorems, equations, proofs, etc.
CONTENT_CLASSES = re.compile(
    r"ltx_(para|theorem|proof|equation|equationgroup|Math|math|"
    r"statement|note|subsection|section|appendix|abstract|"
    r"caption|item|enumerate|itemize|description)",
    re.IGNORECASE,
)

# Tags / classes that are definitely NOT paper body content
JUNK_SELECTORS = [
    "script", "style", "noscript",
    "dialog#modal-form",
    "header.arxiv-html-header", "footer.arxiv-html-footer",
    "nav.ltx_page_navbar", "nav.ltx_TOC",
    "#fixed-buttons-container", "#infobox",
    ".html-header-nav", ".keyboard-glossary", ".ltx_page_logo",
    ".ltx_authors", ".ltx_dates", ".ltx_classification",
    ".ltx_role_email", ".ltx_role_address",
]

_LAST_ARXIV_REQUEST_AT = 0.0


class PipelineState(TypedDict, total=False):
    mode: str
    categories: list[str]
    output_path: str
    max_papers: int
    max_pairs: int
    batch_size: int
    openai_model: str
    pending_papers: list[str] | list[dict[str, Any]]
    current_paper: str
    current_abstract: str
    current_html: str
    current_source_kind: str
    html_segments: list[str]
    validated_records: list[dict[str, Any]]
    translated_records: list[dict[str, Any]]
    formatted_pairs: list[dict[str, str]]
    saved_pairs: int
    seen_hashes: set[str]
    request_delay: float
    max_records_per_paper: int


# ────────────────────────────────────────────────────────────────────────────
# Node: search_papers
# ────────────────────────────────────────────────────────────────────────────
def _build_request_headers(user_agent: str | None = None) -> dict[str, str]:
    if user_agent:
        return {"User-Agent": user_agent}

    contact_email = (
        os.environ.get("ARXIV_CONTACT_EMAIL")
        or os.environ.get("ARXIV_EMAIL")
        or os.environ.get("CONTACT_EMAIL")
        or ""
    ).strip()
    base_agent = "MathAITranslation/1.0"
    if contact_email:
        base_agent = f"{base_agent} ({contact_email})"
    return {"User-Agent": base_agent}


def _parse_retry_after_seconds(header_value: str | None) -> float | None:
    if not header_value:
        return None

    try:
        return max(0.0, float(header_value))
    except ValueError:
        pass

    try:
        retry_at = parsedate_to_datetime(header_value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, retry_at.timestamp() - time.time())


def _wait_for_request_slot(min_interval: float) -> None:
    global _LAST_ARXIV_REQUEST_AT
    if min_interval <= 0:
        return

    now = time.monotonic()
    remaining = (_LAST_ARXIV_REQUEST_AT + min_interval) - now
    if remaining > 0:
        time.sleep(remaining)
    _LAST_ARXIV_REQUEST_AT = time.monotonic()


def _request_with_backoff(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
    min_interval: float = 0.0,
    max_retries: int = ARXIV_MAX_RETRIES,
    label: str = "request",
) -> requests.Response:
    request_headers = _build_request_headers()
    if headers:
        request_headers.update(headers)

    backoff = max(min_interval, ARXIV_MIN_REQUEST_INTERVAL)

    for attempt in range(1, max_retries + 1):
        _wait_for_request_slot(min_interval)

        try:
            response = requests.get(url, params=params, headers=request_headers, timeout=timeout)
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise
            print(
                f"  [warn] [{label}] Request error: {exc}. "
                f"Retrying in {backoff:.1f}s ({attempt}/{max_retries})"
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, ARXIV_MAX_BACKOFF)
            continue

        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
            return response

        wait_seconds = _parse_retry_after_seconds(response.headers.get("Retry-After")) or backoff
        wait_seconds = max(min_interval, wait_seconds)

        if attempt == max_retries:
            response.raise_for_status()

        print(
            f"  [warn] [{label}] HTTP {response.status_code}. "
            f"Retrying in {wait_seconds:.1f}s ({attempt}/{max_retries})"
        )
        time.sleep(wait_seconds)
        backoff = min(max(wait_seconds * 2, backoff * 2), ARXIV_MAX_BACKOFF)

    raise RuntimeError(f"Exhausted retries for {label}")


def _normalize_inline_whitespace(text: str) -> str:
    return " ".join(text.split())


def _strip_quality_markup(text: str) -> str:
    stripped = PLACEHOLDER_PATTERN.sub(" ", text)
    stripped = EQUATION_LABEL_PATTERN.sub(" ", stripped)
    stripped = re.sub(r"\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip()


def _sanitize_latex_residue(text: str) -> str:
    """Strip any raw LaTeX commands that leaked through placeholder replacement."""
    def _keep_group(m: re.Match[str]) -> str:
        # For \emph{X}, \textbf{X} etc. keep the inner text X
        for g in m.groups():
            if g is not None:
                return g
        return ""
    result = RESIDUAL_LATEX_PATTERN.sub(_keep_group, text)
    # Catch any remaining backslash-commands we missed
    result = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", "", result)
    # Remove stray braces left behind
    result = re.sub(r"[{}]", "", result)
    # Collapse whitespace
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _has_math_placeholder(text: str) -> bool:
    """Return True if text contains at least one <MATH_N> placeholder."""
    return bool(MATH_PLACEHOLDER_PATTERN.search(text))


def _placeholder_density(text: str) -> float:
    """Fraction of tokens that are placeholders."""
    tokens = text.split()
    if not tokens:
        return 1.0
    ph_count = sum(1 for t in tokens if PLACEHOLDER_PATTERN.match(t))
    return ph_count / len(tokens)


def _count_latin_words(text: str) -> int:
    return len(LATIN_WORD_PATTERN.findall(_strip_quality_markup(text)))


def _count_arabic_words(text: str) -> int:
    return len(ARABIC_WORD_PATTERN.findall(_strip_quality_markup(text)))


def _placeholders_match(source: str, target: str) -> bool:
    return PLACEHOLDER_PATTERN.findall(source) == PLACEHOLDER_PATTERN.findall(target)


def _is_usable_translation(source: str, target: str, is_equation: bool, mode: str = "full") -> bool:
    normalized_target = _normalize_inline_whitespace(target)
    if not normalized_target or normalized_target.startswith("[TRANSLATION_FAILED]"):
        return False
    
    if mode != "abstract":
        if not _placeholders_match(source, normalized_target):
            return False

    source_latin_words = _count_latin_words(source)
    arabic_words = _count_arabic_words(normalized_target)
    if arabic_words == 0:
        return False

    if mode != "abstract":
        minimum_target_words = 1 if is_equation else max(1, min(4, source_latin_words // 3))
        if arabic_words < minimum_target_words:
            return False

        if source_latin_words and _normalize_inline_whitespace(source) == normalized_target:
            return False
    else:
        if arabic_words < 2:
            return False
        if _normalize_inline_whitespace(source).lower() == normalized_target.lower():
            return False

    return True


def search_papers(state: PipelineState) -> PipelineState:
    query = " OR ".join(f"cat:{category}" for category in state["categories"])
    params = {
        "search_query": query,
        "start": 0,
        "max_results": state["max_papers"],
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    min_interval = max(ARXIV_MIN_REQUEST_INTERVAL, state.get("request_delay", 1.0))
    response = _request_with_backoff(
        ARXIV_API_URL,
        params=params,
        min_interval=min_interval,
        label="arXiv API",
    )

    root = ElementTree.fromstring(response.text)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    
    is_abstract_mode = state.get("mode") == "abstract"
    paper_ids: list[Any] = []

    for entry in root.findall("atom:entry", namespace):
        identifier = entry.findtext("atom:id", default="", namespaces=namespace).strip()
        if identifier:
            paper_id = identifier.rsplit("/", 1)[-1]
            if is_abstract_mode:
                summary = entry.findtext("atom:summary", default="", namespaces=namespace).strip()
                summary = " ".join(summary.split())
                paper_ids.append({"id": paper_id, "abstract": summary})
            else:
                paper_ids.append(paper_id)

    print(f"Found {len(paper_ids)} papers.")
    return {"pending_papers": paper_ids}


# ────────────────────────────────────────────────────────────────────────────
# Node: select_paper
# ────────────────────────────────────────────────────────────────────────────
def select_paper(state: PipelineState) -> PipelineState:
    pending = list(state.get("pending_papers", []))
    if not pending:
        return {"current_paper": "", "current_abstract": "", "validated_records": []}
    current = pending.pop(0)
    if state.get("mode") == "abstract":
        if isinstance(current, dict):
            paper_id = current["id"]
            abstract = current.get("abstract", "")
        else:
            paper_id = current
            abstract = ""
        records = []
        if abstract:
            normalized = " ".join(abstract.split()).strip()
            if normalized:
                records.append({
                    "paper_id": paper_id,
                    "source": normalized,
                    "latex_map": {},
                    "has_math": False,
                    "is_equation": False,
                })
        print(f"  → {paper_id}: compact abstract extracted directly in select_paper")
        return {
            "pending_papers": pending,
            "current_paper": paper_id,
            "current_abstract": abstract,
            "validated_records": records,
        }
    if isinstance(current, dict):
        return {
            "pending_papers": pending,
            "current_paper": current["id"],
            "current_abstract": current.get("abstract", ""),
        }
    return {"pending_papers": pending, "current_paper": current, "current_abstract": ""}


# ────────────────────────────────────────────────────────────────────────────
# Node: fetch_html
# ────────────────────────────────────────────────────────────────────────────
def _is_real_paper_html(html: str) -> bool:
    """
    Return True only when the HTML actually contains a converted paper body.
    ar5iv returns thin error/pending pages for unconverted papers.
    A real conversion always has at least one <math> tag.
    """
    return (
        "<math" in html
        and "ltx_document" in html
        and ("ltx_section" in html or 'class="ltx_p"' in html)
    )


def _decode_text(payload: bytes) -> str:
    for encoding in ("utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="ignore")


def _strip_latex_comments(text: str) -> str:
    return "\n".join(LATEX_COMMENT_PATTERN.sub("", line) for line in text.splitlines())


def _choose_main_tex(tex_sources: dict[str, str]) -> str:
    ranked: list[tuple[int, int, str, str]] = []

    for name, source in tex_sources.items():
        if r"\begin{document}" not in source:
            continue
        score = len(source)
        base_name = Path(name).name.lower()
        if base_name in SOURCE_MAIN_HINTS:
            score += 1_000_000
        if "/" not in name and "\\" not in name:
            score += 100_000
        if r"\title" in source:
            score += 10_000
        ranked.append((score, -len(name), name, source))

    if ranked:
        ranked.sort(reverse=True)
        return ranked[0][3]

    return max(tex_sources.items(), key=lambda item: len(item[1]))[1]


def _extract_tex_source(payload: bytes) -> str | None:
    candidates = [payload]

    try:
        uncompressed = gzip.decompress(payload)
    except OSError:
        uncompressed = b""

    if uncompressed and uncompressed != payload:
        candidates.append(uncompressed)

    for candidate in candidates:
        try:
            with tarfile.open(fileobj=io.BytesIO(candidate), mode="r:*") as archive:
                tex_sources: dict[str, str] = {}
                for member in archive.getmembers():
                    if not member.isfile():
                        continue
                    if Path(member.name).suffix.lower() not in {".tex", ".ltx", ".latex"}:
                        continue
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        continue
                    tex_sources[member.name] = _decode_text(extracted.read())
                if tex_sources:
                    return _choose_main_tex(tex_sources)
        except tarfile.TarError:
            text = _decode_text(candidate)
            if r"\begin{document}" in text:
                return text

    return None


def _extract_latex_body(tex_source: str) -> str:
    body = _strip_latex_comments(tex_source).replace("\r\n", "\n")

    if r"\begin{document}" in body:
        body = body.split(r"\begin{document}", 1)[1]
    if r"\end{document}" in body:
        body = body.split(r"\end{document}", 1)[0]

    body = re.sub(r"\\(?:maketitle|tableofcontents|listoffigures|listoftables)\b", "", body)
    body = re.sub(r"\\begin\{abstract\}.*?\\end\{abstract\}", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"\\abstract\s*\{.*?\}", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.split(
        r"\\begin\{thebibliography\}|\\bibliography\s*\{|\\printbibliography\b",
        body,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    body = re.sub(
        r"\\(?:section|subsection|subsubsection|paragraph|subparagraph)\*?\{([^{}]+)\}",
        r"\n\n\1\n\n",
        body,
    )
    body = re.sub(r"\\label\*?(?:\[[^\]]*\])?\{.*?\}", "", body)
    body = LATEX_REF_PATTERN.sub(" <REF> ", body)
    body = LATEX_CITE_PATTERN.sub(" <CITATION> ", body)
    body = re.sub(r"\\(?:includegraphics|bibliographystyle)\*?(?:\[[^\]]*\])?\{.*?\}", "", body)
    body = re.sub(
        r"\\begin\{(?:figure\*?|table\*?|tikzpicture)\}.*?\\end\{(?:figure\*?|table\*?|tikzpicture)\}",
        "",
        body,
        flags=re.DOTALL,
    )
    body = re.sub(r"\(\s*\)", "", body)
    body = re.sub(r"\[\s*\]", "", body)
    body = re.sub(r"[ \t]+([,.;:!?])", r"\1", body)
    body = re.sub(r"([(\[])[ \t]+", r"\1", body)
    body = re.sub(r"[ \t]+([)\]])", r"\1", body)

    return body.strip()


def _latex_body_to_segments(tex_source: str) -> list[str]:
    body = _extract_latex_body(tex_source)
    if not body:
        return []

    segments: list[str] = []
    for chunk in re.split(r"\n\s*\n+", body):
        normalized = re.sub(r"\s+", " ", chunk).strip()
        if len(normalized) >= 20:
            segments.append(normalized)
    return segments


def _fetch_latex_source(paper_id: str, headers: dict[str, str], delay: float) -> str:
    url = ARXIV_SOURCE_URL.format(paper_id=paper_id)
    try:
        response = _request_with_backoff(
            url,
            headers=headers,
            timeout=30,
            min_interval=max(ARXIV_MIN_REQUEST_INTERVAL, delay),
            label="arxiv/source",
        )
    except requests.RequestException as exc:
        print(f"  âš  [arxiv/source] Could not fetch {paper_id}: {exc}")
        return ""

    tex_source = _extract_tex_source(response.content)
    if not tex_source:
        print(f"  âš  [arxiv/source] {paper_id}: archive fetched but no TeX source found")
        return ""

    print(f"  âœ“ [arxiv/source] Fetched {paper_id} ({len(tex_source)//1024}KB of TeX)")
    return tex_source


def fetch_html(state: PipelineState) -> PipelineState:
    """
    Try ar5iv first; if it has not converted the paper yet, fall back to
    arxiv.org/html which is arXiv's own LaTeXML renderer (same ltx_ classes).
    If neither HTML renderer is ready, fall back to arXiv's source archive.
    """
    current_paper = state.get("current_paper", "")
    if not current_paper:
        return {}

    headers = _build_request_headers()
    delay = state.get("request_delay", 1.0)

    for url_template, source_name, min_interval in [
        (AR5IV_URL, "ar5iv", delay),
        (ARXIV_HTML_URL, "arxiv/html", max(ARXIV_MIN_REQUEST_INTERVAL, delay)),
    ]:
        url = url_template.format(paper_id=current_paper)
        try:
            response = _request_with_backoff(
                url,
                headers=headers,
                timeout=30,
                min_interval=min_interval,
                label=source_name,
            )
        except requests.RequestException as exc:
            print(f"  ⚠ [{source_name}] Could not fetch {current_paper}: {exc}")
            continue

        if _is_real_paper_html(response.text):
            print(f"  ✓ [{source_name}] Fetched {current_paper} ({len(response.text)//1024}KB)")
            return {"current_html": response.text, "current_source_kind": "html"}
        else:
            print(f"  ⚠ [{source_name}] {current_paper}: no math content, trying next source…")

    print(f"  ✗ No HTML source worked for {current_paper}, skipping.")
    tex_source = _fetch_latex_source(current_paper, headers=headers, delay=delay)
    if tex_source:
        return {"current_html": tex_source, "current_source_kind": "latex"}

    print(f"  No HTML or source fallback worked for {current_paper}, skipping.")
    return {"current_html": "", "current_source_kind": ""}


# ────────────────────────────────────────────────────────────────────────────
# Node: extract_text   ← MAIN FIX
# ────────────────────────────────────────────────────────────────────────────
def extract_text(state: PipelineState) -> PipelineState:
    """
    Extract only real paper-body content from ar5iv or arxiv.org/html pages.

    Both sources use the same LaTeXML CSS classes (ltx_*). The key insight
    from inspecting real pages:
      - Equations live in <tr class="ltx_equation ltx_eqn_row …">
      - Prose lives in <p> tags inside <div class="ltx_para">
      - The root container is <article class="ltx_document"> OR just <article>
        OR (on arxiv.org/html) a <section class="ltx_section"> at top level

    We collect TWO kinds of segments:
      1. <p> tags that are inside a content section (ltx_para/theorem/proof…)
      2. <tr class="ltx_equation*"> rows — these contain display math
    """
    source = state.get("current_html", "")
    source_kind = state.get("current_source_kind", "html")
    if not source:
        return {"html_segments": []}

    if source_kind == "latex":
        segments = _latex_body_to_segments(source)
        print(f"  extracted {len(segments)} LaTeX body segments from {state.get('current_paper')}")
        return {"html_segments": segments}

    soup = BeautifulSoup(source, "lxml")

    # ── Step 1: nuke every piece of UI chrome ────────────────────────────
    for selector in JUNK_SELECTORS:
        for el in soup.select(selector):
            el.decompose()

    # Remove abstract (user already has this data)
    for el in soup.find_all(class_=re.compile(r"ltx_abstract", re.I)):
        el.decompose()

    # Remove bibliography / references section
    for el in soup.find_all(class_=re.compile(r"ltx_bibliography", re.I)):
        el.decompose()

    # ── Step 2: find the document root — try multiple selectors ──────────
    # Priority: article.ltx_document > article > div.ltx_document >
    #           div.ltx_page_content > body (last resort)
    doc = (
        soup.find("article", class_=re.compile(r"ltx_document", re.I))
        or soup.find(class_="ltx_document")
        or soup.find("article")
        or soup.find(class_="ltx_page_content")
        or soup.find(class_="ltx_page_main")
        or soup.body
    )

    if doc is None:
        print(f"  ✗ No document root found for {state.get('current_paper')}")
        return {"html_segments": []}

    # ── Step 3: collect paragraph segments ───────────────────────────────
    segments: list[str] = []
    seen_segments: set[str] = set()

    for block in doc.select(BODY_BLOCK_SELECTOR):
        block_classes = " ".join(block.get("class") or [])
        ancestor_classes = " ".join(
            cls
            for ancestor in block.parents
            for cls in (ancestor.get("class") or [])
        )
        in_content = bool(
            CONTENT_CLASSES.search(block_classes) or CONTENT_CLASSES.search(ancestor_classes)
        )
        has_math = bool(block.find("math"))

        if not (in_content or has_math):
            continue

        rendered = str(block)
        text_preview = block.get_text(" ", strip=True)
        if len(text_preview) < 20 or rendered in seen_segments:
            continue
        seen_segments.add(rendered)
        segments.append(rendered)

    if segments:
        print(f"  â†’ {state.get('current_paper')}: {len(segments)} segments extracted")
        return {"html_segments": segments}

    for p in doc.find_all("p"):
        # Walk up to check if this paragraph lives inside a content section
        ancestor_classes = " ".join(
            cls
            for ancestor in p.parents
            for cls in (ancestor.get("class") or [])
        )
        in_content = bool(CONTENT_CLASSES.search(ancestor_classes))
        has_math = bool(p.find("math"))

        if not (in_content or has_math):
            continue
        rendered = str(p)
        if len(rendered) >= 30:
            segments.append(rendered)

    # ── Step 4: collect display-math equation rows ────────────────────────
    # These are <tr class="ltx_equation ltx_eqn_row …"> as seen in the screenshot.
    # We grab the whole <tr> so replace_latex can find the <math alttext="…"> inside.
    for tr in doc.find_all("tr", class_=re.compile(r"ltx_equation", re.I)):
        if tr.find("math"):
            segments.append(str(tr))

    print(f"  → {state.get('current_paper')}: {len(segments)} segments extracted")
    return {"html_segments": segments}


# ────────────────────────────────────────────────────────────────────────────
# Node: replace_latex
# ────────────────────────────────────────────────────────────────────────────
def replace_latex(state: PipelineState) -> PipelineState:
    """
    Replace every <math> element with a placeholder and record the mapping.

    For equation rows (<tr class="ltx_equation…">) we emit the whole
    equation as a single record rather than trying to split it into sentences,
    since display-math blocks are usually standalone statements.
    """
    records: list[dict[str, Any]] = []
    paper_id = state.get("current_paper", "")
    source_kind = state.get("current_source_kind", "html")

    for segment in state.get("html_segments", []):
        mapping: dict[str, str] = {}
        if source_kind == "latex":
            def replace_display(match: re.Match[str]) -> str:
                placeholder = f"<MATH_{len(mapping)}>"
                mapping[placeholder] = match.group(0).strip()
                return placeholder

            def replace_inline(match: re.Match[str]) -> str:
                placeholder = f"<MATH_{len(mapping)}>"
                mapping[placeholder] = match.group(0)
                return placeholder

            full_text = DISPLAY_LATEX_ENV_PATTERN.sub(replace_display, segment)
            full_text = INLINE_LATEX_PATTERN.sub(replace_inline, full_text)
            full_text = " ".join(full_text.split())
            is_equation_row = (
                bool(DISPLAY_LATEX_ENV_PATTERN.search(segment))
                or segment.lstrip().startswith((r"\[", "$$"))
            )

            if is_equation_row:
                if mapping and full_text.strip():
                    records.append({
                        "paper_id": paper_id,
                        "source": full_text.strip(),
                        "latex_map": dict(mapping),
                        "has_math": True,
                        "is_equation": True,
                    })
            else:
                for sentence in SENTENCE_PATTERN.split(full_text):
                    normalized = " ".join(sentence.split()).strip()
                    if normalized:
                        records.append({
                            "paper_id": paper_id,
                            "source": normalized,
                            "latex_map": dict(mapping),
                            "has_math": bool(mapping),
                            "is_equation": False,
                        })
            continue

        soup = BeautifulSoup(segment, "lxml")

        # ── Replace every <math> with a placeholder ───────────────────────
        # ar5iv / arxiv.org/html stores the original LaTeX in alttext="…"
        for math_tag in soup.find_all("math"):
            placeholder = f"<MATH_{len(mapping)}>"
            latex = (math_tag.get("alttext") or math_tag.get_text(" ", strip=True)).strip()
            mapping[placeholder] = latex or placeholder
            math_tag.replace_with(placeholder)

        full_text = soup.get_text(" ", strip=True)
        full_text = " ".join(full_text.split())  # collapse whitespace

        # ── Handle remaining inline LaTeX ($…$) not wrapped in <math> ─────
        def replace_inline(match: re.Match[str]) -> str:
            placeholder = f"<MATH_{len(mapping)}>"
            mapping[placeholder] = match.group(0)
            return placeholder

        full_text = INLINE_LATEX_PATTERN.sub(replace_inline, full_text)
        full_text = " ".join(full_text.split())

        # ── Decide: equation row vs. prose paragraph ──────────────────────
        # Equation rows are emitted as one record (no sentence splitting)
        is_equation_row = "ltx_equation" in segment

        if is_equation_row:
            # Emit the whole block as one record if it has math
            if mapping and full_text.strip():
                records.append({
                    "paper_id": paper_id,
                    "source": full_text.strip(),
                    "latex_map": dict(mapping),
                    "has_math": True,
                    "is_equation": True,
                })
        else:
            # Prose paragraph — split into sentences
            for sentence in SENTENCE_PATTERN.split(full_text):
                normalized = " ".join(sentence.split()).strip()
                if normalized:
                    records.append({
                        "paper_id": paper_id,
                        "source": normalized,
                        "latex_map": dict(mapping),
                        "has_math": bool(mapping),
                        "is_equation": False,
                    })

    return {"validated_records": records}


# ────────────────────────────────────────────────────────────────────────────
# Node: validate
# ────────────────────────────────────────────────────────────────────────────
def validate(state: PipelineState) -> PipelineState:
    """
    Hard filters — drop anything that is clearly not paper body text.
    Every record MUST contain at least one <MATH_N> placeholder.
    Also sanitizes leftover LaTeX and caps records per paper.
    """
    import random as _random
    # Phrases that only appear in web UI / metadata, never in a real paper body
    UI_PHRASES = [
        "arxivlabs", "arxiv.org", "ar5iv",
        "bibliographic and citation tools",
        "recommenders and search tools",
        "download:", "current browse context",
        "terms of use", "open access",
        "submitted on", "last revised",
        "comments:", "journal ref", "doi:",
        "license:", "cite as:", "[submitted",
        "html conversion", "latexml",
        "export bibtex", "bookmark",
    ]

    filtered: list[dict[str, Any]] = []

    if state.get("mode") == "abstract":
        for record in state.get("validated_records", []):
            text = record["source"]
            text_lower = text.lower()

            if len(text) < 20:
                continue

            if _count_latin_words(text) < 6:
                continue

            if any(phrase in text_lower for phrase in UI_PHRASES):
                continue

            filtered.append(record)

        print(f"  -> validate (abstract): {len(state.get('validated_records', []))} -> {len(filtered)} records kept")
        return {"validated_records": filtered}

    for record in state.get("validated_records", []):
        text = record["source"]

        # ── Sanitize leftover LaTeX commands ──────────────────────────────
        text = _sanitize_latex_residue(text)
        record["source"] = text

        text_lower = text.lower()
        is_equation = bool(record.get("is_equation"))
        quality_text = _strip_quality_markup(text)
        latin_word_count = _count_latin_words(text)

        # ── MUST contain at least one <MATH_N> placeholder ────────────────
        if not _has_math_placeholder(text):
            continue

        # ── Length guard ──────────────────────────────────────────────────
        if not (20 <= len(text) <= (1200 if is_equation else 600)):
            continue

        # ── Must contain real English words (not just symbol strings) ─────
        minimum_source_words = 3 if is_equation else 6
        if latin_word_count < minimum_source_words:
            continue

        # ── Placeholder density guard — reject if >65% tokens are placeholders
        if _placeholder_density(text) > 0.65:
            continue

        # ── UI / metadata phrase blocklist ────────────────────────────────
        if any(phrase in text_lower for phrase in UI_PHRASES):
            continue

        # ── Reject lines that are almost entirely placeholders/symbols ────
        if not is_equation and len(quality_text.split()) < 5:
            continue

        # ── Reject reference/citation-style lines ─────────────────────────
        if not is_equation and re.match(
            r"^\s*(\[\d+\]|\(\d{4}\)|Figure\s+\d|Table\s+\d|Remark\s+\d|Proof\.?\s*$)",
            text,
        ):
            continue

        # ── Reject if raw LaTeX still leaked through ─────────────────────
        if re.search(r"\\(?:begin|end|frac|sum|int|prod|lim)\b", text):
            continue

        filtered.append(record)

    # ── Per-paper cap: randomly sample to avoid one large paper dominating ──
    max_per_paper = state.get("max_records_per_paper", 300)
    if len(filtered) > max_per_paper:
        # Keep all equation records first (they're rarer and more valuable),
        # then fill remaining slots with prose records
        eq_records = [r for r in filtered if r.get("is_equation")]
        prose_records = [r for r in filtered if not r.get("is_equation")]
        _random.shuffle(prose_records)
        keep_prose = max(0, max_per_paper - len(eq_records))
        filtered = eq_records + prose_records[:keep_prose]
        _random.shuffle(filtered)

    print(f"  -> validate: {len(state.get('validated_records', []))} -> {len(filtered)} records kept")
    return {"validated_records": filtered}



# ────────────────────────────────────────────────────────────────────────────
# Node: translate  (high-quality domain-expert prompt)
# ────────────────────────────────────────────────────────────────────────────
def translate(state: PipelineState) -> PipelineState:
    load_dotenv(".env")
    api_key = os.environ.get("OPENAI_API_KEY") or state.get("openai_api_key")

    if not api_key:
        raise RuntimeError("No OpenAI API key found. Please check your .env file.")

    client = OpenAI(api_key=api_key)
    records = state.get("validated_records", [])
    translated_records: list[dict[str, Any]] = []
    batch_size = state.get("batch_size", 8)
    mode = state.get("mode", "full")

    if mode == "abstract":
        system_prompt = (
            "You are a senior mathematician fluent in both English and Modern Standard Arabic (MSA). "
            "Translate the English mathematical abstract into formal Arabic, following these rules:\n"
            "1. TERMINOLOGY — use standard Arabic math terms from established textbooks:\n"
            "   theorem→مبرهنة, lemma→لمّة, corollary→نتيجة طبيعية, proof→برهان, "
            "   definition→تعريف, proposition→قضية, conjecture→حدسية, "
            "   function→دالة, equation→معادلة, inequality→متراجحة, "
            "   convergence→تقارب, divergence→تباعد, "
            "   manifold→متعدد طيات, eigenvalue→قيمة ذاتية, "
            "   vector space→فضاء متجهي, subspace→فضاء جزئي, "
            "   homomorphism→تجانس, isomorphism→تماثل, "
            "   integral→تكامل, derivative→مشتقة, partial derivative→مشتقة جزئية, "
            "   topology→طوبولوجيا, algebra→جبر, field→حقل, ring→حلقة, group→زمرة.\n"
            "2. MATH/LATEX — keep all LaTeX formulas, mathematical symbols, variables (e.g., $x$, \\alpha, etc.) EXACTLY as-is. Do NOT translate or alter them.\n"
            "3. STYLE — use formal mathematical Arabic (لغة رياضية فصحى).\n"
            "4. NAMES — keep author/mathematician names in Latin script (Euler, Gauss, etc.).\n"
            "5. OUTPUT — return ONLY a JSON object: {\"translations\": [\"...\"]} with EXACTLY "
            "the same count as input. No markdown, no extra keys, no commentary."
        )
    else:
        system_prompt = (
            "You are a senior mathematician fluent in both English and Modern Standard Arabic (MSA). "
            "Translate each English mathematical sentence into formal Arabic, following these rules:\n"
            "1. TERMINOLOGY — use standard Arabic math terms from established textbooks:\n"
            "   theorem→مبرهنة, lemma→لمّة, corollary→نتيجة طبيعية, proof→برهان, "
            "   definition→تعريف, proposition→قضية, conjecture→حدسية, "
            "   function→دالة, equation→معادلة, inequality→متراجحة, "
            "   convergence→تقارب, divergence→تباعد, "
            "   manifold→متعدد طيات, eigenvalue→قيمة ذاتية, "
            "   vector space→فضاء متجهي, subspace→فضاء جزئي, "
            "   homomorphism→تجانس, isomorphism→تماثل, "
            "   integral→تكامل, derivative→مشتقة, partial derivative→مشتقة جزئية, "
            "   topology→طوبولوجيا, algebra→جبر, field→حقل, ring→حلقة, group→زمرة.\n"
            "2. PLACEHOLDERS — keep ALL <MATH_0>, <MATH_1>, <CITATION>, <REF> EXACTLY as-is. "
            "Do NOT translate, reorder, modify, or remove any placeholder.\n"
            "3. STYLE — use formal mathematical Arabic (لغة رياضية فصحى). "
            "Use proper proof connectors: إذن، وبالتالي، لنفترض أن، نستنتج أن.\n"
            "4. NAMES — keep author/mathematician names in Latin script (Euler, Gauss, etc.).\n"
            "5. OUTPUT — return ONLY a JSON object: {\"translations\": [\"...\", \"...\"]} with EXACTLY "
            "the same count as input. No markdown, no extra keys, no commentary."
        )

    def _call_api(model: str, sources: list[str]) -> list[str] | None:
        try:
            completion = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps({"texts": sources}, ensure_ascii=False)},
                ],
            )
            payload = json.loads(completion.choices[0].message.content or "{}")
            return payload.get("translations")
        except Exception as exc:
            print(f"  [warn] API error: {exc}")
            return None

    def _translate_one(record: dict[str, Any]) -> str:
        source = record["source"]
        is_equation = bool(record.get("is_equation"))
        result = _call_api(state["openai_model"], [source])
        if result and len(result) == 1:
            candidate = str(result[0])
            if _is_usable_translation(source, candidate, is_equation, mode=mode):
                return candidate
        print(f"  [warn] Could not translate cleanly: {source[:60]}...")
        return f"[TRANSLATION_FAILED] {source}"

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        sources = [record["source"] for record in batch]
        translations = _call_api(state["openai_model"], sources)

        if translations is not None and len(translations) != len(batch):
            print(
                f"  [warn] Mismatch on batch {start//batch_size+1}: "
                f"got {len(translations)}, expected {len(batch)}. Retrying..."
            )
            translations = _call_api(state["openai_model"], sources)

        if translations is None or len(translations) != len(batch):
            print(f"  [warn] Falling back to per-sentence translation for batch {start//batch_size+1}...")
            translations = [_translate_one(record) for record in batch]
        else:
            cleaned_translations: list[str] = []
            for record, translation in zip(batch, translations):
                candidate = str(translation)
                if _is_usable_translation(record["source"], candidate, bool(record.get("is_equation")), mode=mode):
                    cleaned_translations.append(candidate)
                    continue
                print(f"  [warn] Retrying weak translation individually: {record['source'][:60]}...")
                cleaned_translations.append(_translate_one(record))
            translations = cleaned_translations

        for record, translation in zip(batch, translations):
            translated_records.append({**record, "target_ar": str(translation)})

    return {"translated_records": translated_records}


def format_pairs(state: PipelineState) -> PipelineState:
    pairs: list[dict[str, str]] = []
    skipped_records = 0
    mode = state.get("mode", "full")

    for record in state.get("translated_records", []):
        source = record["source"]
        target = _normalize_inline_whitespace(str(record["target_ar"]))
        is_equation = bool(record.get("is_equation"))

        if not _is_usable_translation(source, target, is_equation, mode=mode):
            skipped_records += 1
            continue

        if mode != "abstract":
            # ── Post-translation placeholder alignment check ──────────────────
            # Verify that all MATH placeholders in source also appear in target
            source_placeholders = sorted(MATH_PLACEHOLDER_PATTERN.findall(source))
            target_placeholders = sorted(MATH_PLACEHOLDER_PATTERN.findall(target))
            if source_placeholders != target_placeholders:
                skipped_records += 1
                print(f"  [warn] Placeholder mismatch: src={source_placeholders} tgt={target_placeholders}")
                continue

            # ── Must have at least one MATH placeholder in final output ───────
            if not source_placeholders:
                skipped_records += 1
                continue

            # ── Reject if target still contains raw LaTeX ─────────────────────
            if re.search(r"\\(?:begin|end|frac|sum|int|prod|lim)\b", target):
                skipped_records += 1
                continue

        paper_id = record.get("paper_id", "")
        pairs.append({"source": f"<en2ar> {source}", "target": target, "paper_id": paper_id})
        pairs.append({"source": f"<ar2en> {target}", "target": source, "paper_id": paper_id})

    print(f"  -> format_pairs: {len(pairs)} pairs kept, {skipped_records} records skipped")
    return {"formatted_pairs": pairs}


# Node: save
def save(state: PipelineState) -> PipelineState:
    output_path = Path(state["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seen_hashes = state.get("seen_hashes", set())
    saved_pairs = state.get("saved_pairs", 0)
    mode = state.get("mode", "full")

    with output_path.open("a", encoding="utf-8") as handle:
        for pair in state.get("formatted_pairs", []):
            digest = hashlib.sha256(
                f"{pair['source']}||{pair['target']}".encode("utf-8")
            ).hexdigest()
            if digest in seen_hashes:
                continue
            # Write without the paper_id field to keep the JSONL clean
            handle.write(
                json.dumps(
                    {"source": pair["source"], "target": pair["target"]},
                    ensure_ascii=False,
                )
                + "\n"
            )
            seen_hashes.add(digest)
            saved_pairs += 1
            if mode != "abstract" and saved_pairs >= state["max_pairs"]:
                break

    print(f"  → saved_pairs total: {saved_pairs}")
    return {"seen_hashes": seen_hashes, "saved_pairs": saved_pairs}


# ────────────────────────────────────────────────────────────────────────────
# Routing
# ────────────────────────────────────────────────────────────────────────────
def should_continue(state: PipelineState) -> str:
    if state.get("mode") == "abstract":
        if state.get("pending_papers"):
            return "select_paper"
        return END
    if state.get("saved_pairs", 0) >= state["max_pairs"]:
        return END
    if state.get("pending_papers"):
        return "select_paper"
    return END


# ────────────────────────────────────────────────────────────────────────────
# Graph
# ────────────────────────────────────────────────────────────────────────────
def build_graph(mode: str = "full") -> Any:
    graph = StateGraph(PipelineState)
    graph.add_node("search_papers", search_papers)
    graph.add_node("select_paper", select_paper)
    graph.add_node("validate", validate)
    graph.add_node("translate", translate)
    graph.add_node("format_pairs", format_pairs)
    graph.add_node("save", save)

    if mode == "full":
        graph.add_node("extract_text", extract_text)
        graph.add_node("fetch_html", fetch_html)
        graph.add_node("replace_latex", replace_latex)

        graph.add_edge(START, "search_papers")
        graph.add_edge("search_papers", "select_paper")
        graph.add_edge("select_paper", "fetch_html")
        graph.add_edge("fetch_html", "extract_text")
        graph.add_edge("extract_text", "replace_latex")
        graph.add_edge("replace_latex", "validate")
    else:
        graph.add_edge(START, "search_papers")
        graph.add_edge("search_papers", "select_paper")
        graph.add_edge("select_paper", "validate")

    graph.add_edge("validate", "translate")
    graph.add_edge("translate", "format_pairs")
    graph.add_edge("format_pairs", "save")
    graph.add_conditional_edges(
        "save", should_continue, {"select_paper": "select_paper", END: END}
    )
    return graph.compile()


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape LaTeX-aware math pairs from arXiv paper bodies or abstracts."
    )
    parser.add_argument("--mode", choices=["full", "abstract"], default="full",
                        help="Extraction mode: 'full' (scrapes body with LaTeX placeholders) "
                             "or 'abstract' (scrapes only abstracts, keeps LaTeX intact)")
    parser.add_argument("--output", default=None,
                        help="Output JSONL file path. Defaults to data/phase2_latex_dataset.jsonl for full mode, "
                             "or data/phase1_final_dataset.jsonl for abstract mode.")
    parser.add_argument("--max-papers", type=int, default=150)
    parser.add_argument("--max-pairs", type=int, default=20000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--openai-model", default="gpt-4o")
    parser.add_argument("--request-delay", type=float, default=1.0)
    parser.add_argument("--max-records-per-paper", type=int, default=40,
                        help="Max records to translate per paper (random sample). "
                             "Prevents one large paper from dominating cost/dataset.")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=[
            # Pure Mathematics
            "math.AG",  # Algebraic Geometry
            "math.NT",  # Number Theory
            "math.AT",  # Algebraic Topology
            "math.CT",  # Category Theory
            "math.GR",  # Group Theory
            "math.RA",  # Rings and Algebras
            "math.RT",  # Representation Theory
            "math.AC",  # Commutative Algebra
            # Analysis
            "math.AP",  # Analysis of PDEs
            "math.CA",  # Classical Analysis & ODEs
            "math.FA",  # Functional Analysis
            "math.CV",  # Complex Variables
            "math.SP",  # Spectral Theory
            # Geometry & Topology
            "math.DG",  # Differential Geometry
            "math.GT",  # Geometric Topology
            "math.MG",  # Metric Geometry
            "math.SG",  # Symplectic Geometry
            # Discrete / Applied
            "math.CO",  # Combinatorics
            "math.LO",  # Logic
            "math.NA",  # Numerical Analysis
            "math.OC",  # Optimization & Control
            "math.PR",  # Probability
            "math.ST",  # Statistics Theory
            "math.DS",  # Dynamical Systems
            "math.QA",  # Quantum Algebra
        ],
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Set default output based on mode if not specified
    output_path = args.output
    if output_path is None:
        if args.mode == "abstract":
            output_path = "data/phase1_final_dataset.jsonl"
        else:
            output_path = "data/phase2_latex_dataset.jsonl"

    graph = build_graph(args.mode)
    initial_state: PipelineState = {
        "mode": args.mode,
        "categories": args.categories,
        "output_path": output_path,
        "max_papers": args.max_papers,
        "max_pairs": args.max_pairs,
        "batch_size": args.batch_size,
        "openai_model": args.openai_model,
        "saved_pairs": 0,
        "seen_hashes": set(),
        "request_delay": args.request_delay,
        "max_records_per_paper": args.max_records_per_paper,
        "openai_api_key": None,
    }
    final_state = graph.invoke(initial_state)
    print(
        json.dumps(
            {
                "output_path": output_path,
                "saved_pairs": final_state.get("saved_pairs", 0),
                "remaining_papers": len(final_state.get("pending_papers", [])),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
