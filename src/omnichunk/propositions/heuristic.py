"""
Heuristic proposition extraction — regex over sentences, zero extra dependencies.

Segmentation is structure-aware: it splits on sentence terminators and
semicolons but deliberately does *not* break inside parenthetical asides,
quoted speech, decimal numbers, or numbered-list markers. Numbered list items
each become their own proposition.
"""

from __future__ import annotations

import re
from typing import Any

from omnichunk.propositions.types import Proposition
from omnichunk.types import ByteRange
from omnichunk.util.text_index import TextIndex

# Classification patterns: (name, regex, base_confidence). Applied to an
# already-segmented proposition to label it and assign a confidence.
_CLASSIFIERS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("copula_is", re.compile(r"\b[A-Z][\w]*(?:\s+\w+){0,6}\s+is\s+\S"), 0.72),
    ("defined_as", re.compile(r"^[A-Z][^:\n]{1,64}:\s*\S"), 0.65),
    (
        "numeric_claim",
        re.compile(
            r"\b(?:approximately|about|over|under|at least|more than|less than)\s+[\d,]",
            re.IGNORECASE,
        ),
        0.58,
    ),
    ("year_claim", re.compile(r"\b(?:in|since|until|before|after)\s+(?:the\s+)?\d{4}\b"), 0.55),
    ("list_item", re.compile(r"^\s*\d+[.)]\s"), 0.60),
)

_LIST_MARKER = re.compile(r"(?m)^([ \t]*)(\d+)[.)]\s")
_OPEN = "([{"
_CLOSE = ")]}"
_QUOTE_OPEN = '"“'  # straight + left curly double quote
_QUOTE_CLOSE = '"”'  # straight + right curly double quote


def _list_markers(text: str) -> tuple[set[int], set[int]]:
    """Return (list-number period indices, list-item start indices)."""
    periods: set[int] = set()
    starts: set[int] = set()
    for m in _LIST_MARKER.finditer(text):
        digit_start = m.start() + len(m.group(1))
        starts.add(digit_start)
        periods.add(m.start(2) + len(m.group(2)))  # index of the '.' or ')'
    return periods, starts


def _segment_spans(text: str) -> list[tuple[int, int]]:
    """Split text into proposition char spans, respecting structure."""
    n = len(text)
    list_periods, item_starts = _list_markers(text)

    spans: list[tuple[int, int]] = []
    start = 0
    i = 0
    depth = 0
    quote: str | None = None

    while i < n:
        ch = text[i]

        if quote is not None:
            # Inside quoted speech: only a matching close quote ends it.
            if ch == quote or (quote == '"' and ch == '"') or ch in _QUOTE_CLOSE:
                quote = None
            i += 1
            continue

        # A numbered list item forces a fresh proposition at its marker.
        if i in item_starts and i > start:
            spans.append((start, i))
            start = i

        if ch in _QUOTE_OPEN:
            quote = '"' if ch == '"' else "”"
            i += 1
            continue
        if ch in _OPEN:
            depth += 1
            i += 1
            continue
        if ch in _CLOSE:
            depth = max(0, depth - 1)
            i += 1
            continue

        if depth == 0:
            if ch == ";":
                spans.append((start, i + 1))
                start = i + 1
                i += 1
                continue
            if ch in ".!?":
                prev = text[i - 1] if i > 0 else ""
                nxt = text[i + 1] if i + 1 < n else ""
                # Decimal point inside a number: not a boundary.
                if ch == "." and prev.isdigit() and nxt.isdigit():
                    i += 1
                    continue
                # Numbered-list marker period: not a boundary.
                if i in list_periods:
                    i += 1
                    continue
                # Sentence terminator only when followed by space or end of text.
                if nxt == "" or nxt.isspace():
                    spans.append((start, i + 1))
                    start = i + 1
                    i += 1
                    continue
        i += 1

    if start < n:
        spans.append((start, n))
    return spans


def _trim(text: str, a: int, b: int) -> tuple[int, int]:
    """Shrink [a, b) past surrounding whitespace without changing the slice."""
    while a < b and text[a].isspace():
        a += 1
    while b > a and text[b - 1].isspace():
        b -= 1
    return a, b


def _classify(snippet: str) -> tuple[str, float]:
    for name, rx, conf in _CLASSIFIERS:
        if rx.search(snippet):
            return name, conf
    return "clause", 0.50


def extract_propositions_heuristic(filepath: str, text: str) -> list[Proposition]:
    """Extract atomic propositions, one per structural clause / list item."""
    if not text.strip():
        return []

    ti = TextIndex(text)
    out: list[Proposition] = []
    seen: set[tuple[int, int]] = set()

    for a0, b0 in _segment_spans(text):
        a, b = _trim(text, a0, b0)
        if a >= b:
            continue
        snippet = text[a:b]
        # Skip fragments with no alphanumeric content (stray punctuation).
        if not re.search(r"[A-Za-z0-9]", snippet):
            continue
        if (a, b) in seen:
            continue
        seen.add((a, b))
        bs = ti.byte_offset_for_char(a)
        be = ti.byte_offset_for_char(b)
        pattern, conf = _classify(snippet)
        meta: dict[str, Any] = {"pattern": pattern, "filepath": filepath}
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
