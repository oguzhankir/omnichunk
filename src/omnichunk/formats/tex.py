from __future__ import annotations

import re
from typing import Literal

from omnichunk.formats.types import FormatSegment, LoadedDocument

_CODE_ENV_PATTERN = re.compile(
    r"\\begin\{(lstlisting|verbatim|minted)\}"
    r"(?:\[(?P<opts>[^\]]*)\])?"
    r"([\s\S]*?)"
    r"\\end\{\1\}",
)

_MATH_ENV_PATTERN = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray|displaymath|math)\*?\}"
    r"[\s\S]*?"
    r"\\end\{\1\*?\}",
)

# Display math \[...\] and inline math $...$ / \(...\) — atomic; never split.
_MATH_DISPLAY_BRACKET = re.compile(r"\\\[[\s\S]*?\\\]")
_MATH_DISPLAY_DOLLARS = re.compile(r"\$\$[\s\S]*?\$\$")
_MATH_INLINE_PAREN = re.compile(r"\\\([\s\S]*?\\\)")

_LABEL_PATTERN = re.compile(r"\\label\{([^}]+)\}")
_BIBLIOGRAPHY_PATTERN = re.compile(r"\\(bibliography|bibliographystyle)\{([^}]+)\}")

_SECTION_PATTERN = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection)\*?\{([^}]*)\}",
)


def _lstlisting_language(opts: str | None) -> str | None:
    if not opts:
        return None
    m = re.search(r"language\s*=\s*([A-Za-z][\w+]*)", opts)
    return m.group(1).lower() if m else None


def load_latex(content: str) -> LoadedDocument:
    """Split LaTeX into prose and code (verbatim-like) segments."""
    warnings: list[str] = []
    text = content
    segments: list[FormatSegment] = []

    if _unbalanced_begin_end(text):
        warnings.append("possible_unbalanced_begin_end")

    # Collect all atomic regions in one pass: code envs + math envs + display/inline math.
    SegKind = Literal["prose", "code"]
    atomic: list[tuple[int, int, SegKind, dict[str, object]]] = []

    for match in _CODE_ENV_PATTERN.finditer(text):
        env = match.group(1)
        opts = match.groupdict().get("opts")
        lang = _lstlisting_language(opts)
        meta: dict[str, object] = {"latex_env": env}
        if lang:
            meta["latex_language"] = lang
        atomic.append((match.start(), match.end(), "code", meta))

    for match in _MATH_ENV_PATTERN.finditer(text):
        atomic.append(
            (
                match.start(),
                match.end(),
                "prose",
                {"latex_math": match.group(1)},
            )
        )

    for math_re, label in (
        (_MATH_DISPLAY_BRACKET, "display_bracket"),
        (_MATH_DISPLAY_DOLLARS, "display_dollars"),
        (_MATH_INLINE_PAREN, "inline_paren"),
    ):
        for match in math_re.finditer(text):
            atomic.append(
                (match.start(), match.end(), "prose", {"latex_math": label})
            )

    # Resolve overlaps deterministically: keep the longest, drop the rest.
    atomic.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    deduped: list[tuple[int, int, Literal["prose", "code"], dict[str, object]]] = []
    last_end = -1
    for s, e, kind, meta in atomic:
        if s < last_end:
            continue
        deduped.append((s, e, kind, meta))
        last_end = e

    last = 0
    for s, e, kind, meta in deduped:
        if s > last:
            _append_tex_prose_segments(text[last:s], last, segments, text)
        segments.append(
            FormatSegment(char_start=s, char_end=e, kind=kind, metadata=meta)
        )
        last = e

    if last < len(text):
        _append_tex_prose_segments(text[last:], last, segments, text)

    # Reconstruction invariant: chunk_loaded_document drops whitespace-only
    # segments. Math blocks and atomic environments often have whitespace
    # boundaries that would otherwise vanish from the output. Merge any
    # uncovered gap into the closest non-empty neighbour by extending its
    # range. We prefer extending the LEFT neighbour so byte ranges grow
    # forward.
    segments.sort(key=lambda seg: seg.char_start)
    if segments:
        adjusted: list[FormatSegment] = []
        cursor = 0
        for seg in segments:
            if seg.char_start > cursor:
                # Stretch the previous segment forward into the gap if we
                # already have one; otherwise stretch the current one back.
                if adjusted:
                    prev = adjusted[-1]
                    adjusted[-1] = FormatSegment(
                        char_start=prev.char_start,
                        char_end=seg.char_start,
                        kind=prev.kind,
                        metadata=prev.metadata,
                    )
                else:
                    seg = FormatSegment(
                        char_start=cursor,
                        char_end=seg.char_end,
                        kind=seg.kind,
                        metadata=seg.metadata,
                    )
            adjusted.append(seg)
            cursor = max(cursor, seg.char_end)
        if cursor < len(text):
            prev = adjusted[-1]
            adjusted[-1] = FormatSegment(
                char_start=prev.char_start,
                char_end=len(text),
                kind=prev.kind,
                metadata=prev.metadata,
            )
        segments = adjusted

    ordered = sorted(segments, key=lambda s: s.char_start)
    # Reconstruction invariant: the chunk engine concatenates the segment
    # spans verbatim. We must not drop whitespace-only gaps between math
    # blocks (or any other atomic span), so we keep ALL non-empty segments.
    filtered = tuple(s for s in ordered if s.char_end > s.char_start)

    return LoadedDocument(
        text=text,
        segments=filtered,
        format_name="latex",
        warnings=tuple(warnings),
    )


def _unbalanced_begin_end(text: str) -> bool:
    begins = len(re.findall(r"\\begin\{", text))
    ends = len(re.findall(r"\\end\{", text))
    return begins != ends


def _append_tex_prose_segments(
    prose: str,
    base_offset: int,
    segments: list[FormatSegment],
    full_text: str,
) -> None:
    """Split prose regions by section commands for sharper chunk boundaries."""
    if not prose:
        return

    sec_iter = list(_SECTION_PATTERN.finditer(prose))
    if not sec_iter:
        start = base_offset
        end = base_offset + len(prose)
        if full_text[start:end].strip():
            segments.append(
                FormatSegment(
                    char_start=start,
                    char_end=end,
                    kind="prose",
                    metadata={"latex": "body"},
                )
            )
        return

    pos = 0
    for m in sec_iter:
        if m.start() > pos:
            chunk = prose[pos : m.start()]
            if chunk.strip():
                segments.append(
                    FormatSegment(
                        char_start=base_offset + pos,
                        char_end=base_offset + m.start(),
                        kind="prose",
                        metadata={"latex": "preamble_segment"},
                    )
                )
        title = m.group(1)
        segments.append(
            FormatSegment(
                char_start=base_offset + m.start(),
                char_end=base_offset + m.end(),
                kind="prose",
                metadata={"latex": "section_heading", "title": title},
            )
        )
        pos = m.end()

    if pos < len(prose):
        tail = prose[pos:]
        if tail.strip():
            segments.append(
                FormatSegment(
                    char_start=base_offset + pos,
                    char_end=base_offset + len(prose),
                    kind="prose",
                    metadata={"latex": "post_section"},
                )
            )

