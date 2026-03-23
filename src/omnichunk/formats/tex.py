from __future__ import annotations

import re

from omnichunk.formats.types import FormatSegment, LoadedDocument

_CODE_ENV_PATTERN = re.compile(
    r"\\begin\{(lstlisting|verbatim|minted)\}"
    r"(?:\[[^\]]*\])?"
    r"([\s\S]*?)"
    r"\\end\{\1\}",
)

_SECTION_PATTERN = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection)\*?\{([^}]*)\}",
)


def load_latex(content: str) -> LoadedDocument:
    """Split LaTeX into prose and code (verbatim-like) segments."""
    warnings: list[str] = []
    text = content
    segments: list[FormatSegment] = []

    if _unbalanced_begin_end(text):
        warnings.append("possible_unbalanced_begin_end")

    last = 0
    for match in _CODE_ENV_PATTERN.finditer(text):
        if match.start() > last:
            prose = text[last : match.start()]
            _append_tex_prose_segments(prose, last, segments, text)
        env = match.group(1)
        start = match.start()
        end = match.end()
        segments.append(
            FormatSegment(
                char_start=start,
                char_end=end,
                kind="code",
                metadata={"latex_env": env},
            )
        )
        last = end

    if last < len(text):
        prose = text[last:]
        _append_tex_prose_segments(prose, last, segments, text)

    ordered = sorted(segments, key=lambda s: s.char_start)
    filtered = tuple(
        s
        for s in ordered
        if s.char_end > s.char_start and text[s.char_start : s.char_end].strip()
    )

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

