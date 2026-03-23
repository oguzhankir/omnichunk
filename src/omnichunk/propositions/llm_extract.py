"""Optional LLM-backed proposition extraction (user-supplied ``llm_fn``)."""

from __future__ import annotations

import json
from collections.abc import Callable

from omnichunk.propositions.types import Proposition
from omnichunk.types import ByteRange
from omnichunk.util.text_index import TextIndex


def _find_span_bytes(ti: TextIndex, full: str, quote: str) -> tuple[int, int] | None:
    if not quote.strip():
        return None
    idx = full.find(quote)
    if idx < 0:
        return None
    c0, c1 = idx, idx + len(quote)
    return ti.byte_offset_for_char(c0), ti.byte_offset_for_char(c1)


def extract_propositions_llm(
    filepath: str,
    text: str,
    *,
    llm_fn: Callable[[str, str], str],
) -> tuple[list[Proposition], list[str]]:
    """
    Ask ``llm_fn(filepath, text)`` for JSON: ``{\"claims\": [{\"text\": \"...\"}, ...]}``.
    Each claim must appear verbatim in ``text``; otherwise it is skipped and a warning is recorded.
    """
    raw = llm_fn(filepath, text)
    warnings: list[str] = []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return [], [f"llm_fn returned invalid JSON: {e}"]

    claims = data.get("claims")
    if not isinstance(claims, list):
        return [], ["llm_fn JSON must contain a list 'claims'"]

    ti = TextIndex(text)
    out: list[Proposition] = []
    for i, item in enumerate(claims):
        if not isinstance(item, dict):
            warnings.append(f"claim[{i}] is not an object")
            continue
        qt = item.get("text")
        if not isinstance(qt, str) or not qt.strip():
            warnings.append(f"claim[{i}] missing string 'text'")
            continue
        span = _find_span_bytes(ti, text, qt)
        if span is None:
            warnings.append(f"claim[{i}] text not found verbatim in source")
            continue
        bs, be = span
        out.append(
            Proposition(
                text=qt.strip(),
                byte_range=ByteRange(start=bs, end=be),
                confidence=float(item.get("confidence", 0.7)),
                metadata={"source": "llm", "filepath": filepath, "index": i},
            )
        )

    out.sort(key=lambda p: (p.byte_range.start, p.byte_range.end))
    return out, warnings
