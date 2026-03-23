from __future__ import annotations

import importlib
import io
import re
from typing import Literal

from omnichunk.formats.types import FormatSegment, LoadedDocument


def load_pdf_bytes(raw: bytes) -> LoadedDocument:
    """Extract text from PDF bytes; one segment per page (full text coverage)."""
    try:
        PdfReader = importlib.import_module("pypdf").PdfReader
    except ImportError as exc:
        raise ImportError(
            "PDF support requires pypdf. Install with: pip install omnichunk[pdf]"
        ) from exc

    warnings: list[str] = []
    reader = PdfReader(io.BytesIO(raw))
    page_texts: list[str] = []
    for page in reader.pages:
        extracted = ""
        try:
            extracted = page.extract_text(extraction_mode="layout")
        except (TypeError, Exception):
            try:
                extracted = page.extract_text()
            except Exception:
                extracted = ""
        page_texts.append(extracted or "")

    parts: list[str] = []
    segments: list[FormatSegment] = []
    cursor = 0

    for i, page_text in enumerate(page_texts):
        sep = f"\n\n--- page {i + 1} ---\n\n" if i > 0 else ""
        block = sep + page_text
        start = cursor
        parts.append(block)
        cursor += len(block)
        if not block.strip():
            continue
        kind: Literal["prose", "code"] = "code" if _looks_code_like(page_text) else "prose"
        segments.append(
            FormatSegment(
                char_start=start,
                char_end=cursor,
                kind=kind,
                metadata={"page": i + 1, "pdf": True},
            )
        )

    full_text = "".join(parts)
    if not segments and full_text.strip():
        segments.append(
            FormatSegment(
                char_start=0,
                char_end=len(full_text),
                kind="prose",
                metadata={"page": 1, "pdf": True, "fallback": "full_document"},
            )
        )

    filtered = tuple(
        s
        for s in segments
        if s.char_end > s.char_start and full_text[s.char_start : s.char_end].strip()
    )

    if not page_texts:
        warnings.append("empty_pdf")

    return LoadedDocument(
        text=full_text,
        segments=filtered,
        format_name="pdf",
        warnings=tuple(warnings),
    )


def _looks_code_like(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if "```" in t or t.count("`") >= 2:
        return True
    lines = [ln for ln in t.split("\n") if ln.strip()]
    if len(lines) < 2:
        return bool(
            re.search(r"\b(def|class|import|from|return|const|let|function|fn|impl)\b", t)
        )
    if t.count(";") >= 2 or (t.count("{") + t.count("}") >= 4):
        return True
    indented = sum(1 for ln in lines if re.match(r"^ {2,}\S", ln) or re.match(r"^\t+\S", ln))
    return indented >= max(2, len(lines) // 3)
