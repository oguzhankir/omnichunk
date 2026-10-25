from __future__ import annotations

import re
from collections.abc import Callable

_BOUNDARY_CANDIDATES = re.compile(
    r"(?P<paragraph>\r?\n[\t ]*\r?\n(?:[\t ]*\r?\n)*)|(?P<punctuation>[.!?。！？]+)"
)
_CJK_TERMINATORS = frozenset("。！？")
_CLOSING_DELIMITERS = frozenset("\"')]}”’»」』】）〕〉》")
_OPENING_DELIMITERS = frozenset("\"'([{“‘«「『【（〔〈《")


def _is_sentence_start(char: str) -> bool:
    # Case-less scripts have no uppercase starter; ASCII lowercase continuations
    # retain the conservative behavior of the original heuristic.
    return (
        char.isupper()
        or (char.isalpha() and char.lower() == char.upper())
        or char.isdigit()
        or char in _OPENING_DELIMITERS
    )


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
    for match in _BOUNDARY_CANDIDATES.finditer(text):
        if match.start() < pos:
            continue
        end = match.end()
        if match.lastgroup == "punctuation":
            while end < n and text[end] in _CLOSING_DELIMITERS:
                end += 1
            whitespace_start = end
            while end < n and text[end].isspace():
                end += 1
            # Requiring whitespace avoids splitting decimal numbers,
            # versions, URLs and identifiers at an internal period.
            if (
                not any(char in _CJK_TERMINATORS for char in match.group())
                and end < n
                and (end == whitespace_start or not _is_sentence_start(text[end]))
            ):
                continue
        parts.append((text[pos:end], pos, end))
        pos = end
    if pos < n:
        parts.append((text[pos:], pos, n))
    return _collapse_empty_triples(parts, full_text=text)


def split_sentences(
    text: str,
    *,
    splitter_fn: Callable[[str], list[str]] | None = None,
) -> list[tuple[str, int, int]]:
    """Split text into sentences, returning (sentence_text, char_start, char_end) triples.

    If splitter_fn is provided, it is called with the full text and must return
    a list of sentence strings that reconstruct the source exactly. The function
    maps them back to character offsets in source order, without re-encoding.

    The dependency-free default is a heuristic: ASCII .!? requires whitespace
    followed by an uppercase letter, an uncased letter, a digit or an opening
    delimiter. Japanese/Chinese 。！？ also splits without whitespace. Closing
    quotes/brackets and following whitespace stay with the preceding sentence.
    Blank lines (including CRLF) always split. Abbreviations and other ambiguous
    linguistic boundaries require a caller-provided splitter.

    If nltk is installed and splitter_fn is None, the caller may optionally
    adapt nltk.tokenize.sent_tokenize to retain whitespace before passing it as
    splitter_fn. A splitter that discards source characters is rejected.

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
