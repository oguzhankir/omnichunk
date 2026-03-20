from __future__ import annotations

import re
from collections.abc import Callable

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])")
_PARA_SPLIT = re.compile(r"\n\n+")


def _collapse_empty_triples(
    triples: list[tuple[str, int, int]],
    *,
    full_text: str,
) -> list[tuple[str, int, int]]:
    if not triples:
        return [("", 0, len(full_text))] if full_text == "" else []
    merged: list[tuple[str, int, int]] = []
    for s, a, b in triples:
        if s == "":
            if merged:
                ps, pa, _ = merged[-1]
                merged[-1] = (ps + s, pa, b)
            else:
                merged.append((s, a, b))
        else:
            if merged and merged[-1][0] == "":
                zs, za, _ = merged.pop()
                merged.append((zs + s, za, b))
            else:
                merged.append((s, a, b))
    joined = "".join(s for s, _, _ in merged)
    if joined != full_text:
        raise ValueError("sentence split failed reconstruction invariant")
    return merged


def _default_split_triples(text: str) -> list[tuple[str, int, int]]:
    if not text:
        return [("", 0, 0)]
    parts: list[tuple[str, int, int]] = []
    pos = 0
    n = len(text)
    while pos < n:
        m_para = _PARA_SPLIT.search(text, pos)
        m_sent = _SENT_SPLIT.search(text, pos)
        p_start = m_para.start() if m_para else n + 1
        s_start = m_sent.start() if m_sent else n + 1
        if m_para is not None and p_start <= s_start:
            end = m_para.end()
            parts.append((text[pos:end], pos, end))
            pos = end
        elif m_sent is not None:
            end = m_sent.end()
            parts.append((text[pos:end], pos, end))
            pos = m_sent.end()
        else:
            parts.append((text[pos:], pos, n))
            pos = n
    return _collapse_empty_triples(parts, full_text=text)


def split_sentences(
    text: str,
    *,
    splitter_fn: Callable[[str], list[str]] | None = None,
) -> list[tuple[str, int, int]]:
    """Split text into sentences, returning (sentence_text, char_start, char_end) triples.

    If splitter_fn is provided, it is called with the full text and must return
    a list of sentence strings. The function then maps them back to byte offsets
    using a linear scan (no re-encode; O(N) over chars).

    Default splitter: regex-based, splits on sentence-ending punctuation
    (.!?) followed by whitespace + capital letter OR end of string.
    Does NOT depend on nltk.

    If nltk is installed and splitter_fn is None, the caller may optionally
    pass nltk.tokenize.sent_tokenize as splitter_fn for better accuracy.

    Returns list of (sentence_text, char_start, char_end) where
    char_start is inclusive, char_end is exclusive.
    All returned ranges must cover the full text contiguously.
    Empty strings are merged into the previous sentence, or the next if first.
    """
    if splitter_fn is None:
        return _default_split_triples(text)

    strings = splitter_fn(text)
    out: list[tuple[str, int, int]] = []
    cursor = 0
    for s in strings:
        if s == "":
            if out:
                ps, a, b = out[-1]
                out[-1] = (ps + s, a, b)
            else:
                out.append((s, cursor, cursor))
            continue
        idx = text.find(s, cursor)
        if idx < 0:
            raise ValueError(
                "splitter_fn produced a sentence not found in order in the source text"
            )
        end = idx + len(s)
        out.append((s, idx, end))
        cursor = end
    if cursor != len(text):
        raise ValueError("splitter_fn sentences do not cover the full text")
    return _collapse_empty_triples(out, full_text=text)
