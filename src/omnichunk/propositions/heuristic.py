"""
Heuristic proposition extraction — regex over sentences, zero extra dependencies.
"""

from __future__ import annotations

import re
from typing import Any

from omnichunk.propositions.types import Proposition
from omnichunk.semantic.sentences import split_sentences
from omnichunk.types import ByteRange
from omnichunk.util.text_index import TextIndex

# Patterns: (name, regex, base_confidence)
_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    (
        "copula_is",
        re.compile(
            r"\b([A-Z][a-z]+(?:\s+[a-z]+){0,6})\s+is\s+([^\.!?]+(?:\.|$))",
            re.MULTILINE,
        ),
        0.72,
    ),
    (
        "defined_as",
        re.compile(
            r"\b([A-Z][^\n:]{1,64})\s*:\s*([^\n]+)",
            re.MULTILINE,
        ),
        0.65,
    ),
    (
        "numeric_claim",
        re.compile(
            r"\b(?:approximately|about|over|under|at least|more than|less than)\s+"
            r"[\d,]+(?:\.\d+)?%?\b[^\.!?]*[\.!?]",
            re.IGNORECASE,
        ),
        0.58,
    ),
    (
        "year_claim",
        re.compile(r"\b(?:in|since|until|before|after)\s+(?:the\s+)?(?:year\s+)?\d{4}\b[^\.!?]*[\.!?]"),
        0.55,
    ),
)


def extract_propositions_heuristic(filepath: str, text: str) -> list[Proposition]:
    """Extract propositions using sentence split + lightweight regex patterns."""
    if not text.strip():
        return []

    ti = TextIndex(text)
    sents = split_sentences(text)
    out: list[Proposition] = []
    seen: set[tuple[int, int]] = set()

    for sent, c0, _c1 in sents:
        if not sent.strip():
            continue
        for pname, rx, base in _PATTERNS:
            for m in rx.finditer(sent):
                a, b = m.span()
                abs_start = c0 + a
                abs_end = c0 + b
                span = (abs_start, abs_end)
                if span in seen:
                    continue
                seen.add(span)
                snippet = text[abs_start:abs_end].strip()
                if not snippet:
                    continue
                bs = ti.byte_offset_for_char(abs_start)
                be = ti.byte_offset_for_char(abs_end)
                meta: dict[str, Any] = {
                    "pattern": pname,
                    "filepath": filepath,
                }
                conf = min(0.95, base + 0.03 * min(len(snippet), 120) / 120.0)
                out.append(
                    Proposition(
                        text=snippet,
                        byte_range=ByteRange(start=bs, end=be),
                        confidence=round(conf, 4),
                        metadata=meta,
                    )
                )

    out.sort(key=lambda p: (p.byte_range.start, p.byte_range.end, p.text))
    return out
