"""Minimal reStructuredText loader.

The chunker delegates ``.rst`` files to this module (similar to LaTeX),
producing a :class:`LoadedDocument` whose segments capture:

- ``.. code-block:: <lang>`` and ``.. literalinclude::`` directives as
  ``kind='code'`` so the code engine can take over.
- Prose between them as ``kind='prose'``.

We deliberately keep this regex-driven so we never pull in an
``rst2html`` / ``docutils`` runtime dependency.
"""

from __future__ import annotations

import re

from omnichunk.formats.types import FormatSegment, LoadedDocument

# .. code-block:: <lang>  /  .. sourcecode:: <lang>  /  .. literalinclude:: <path>
_CODE_DIRECTIVE_RE = re.compile(
    r"(?ms)^\.\.\s+(code-block|sourcecode|literalinclude)::\s*(?P<lang>\S*)\s*\n"
    r"(?:^\s+:[^\n]*\n)*"
    r"(?P<body>(?:^\s+[^\n]*\n|^\s*\n)*?)"
    r"(?=^\S|\Z)"
)

# .. note:: / .. warning:: / .. tip:: / .. toctree:: — non-code directives we surface as prose.
_GENERIC_DIRECTIVE_RE = re.compile(
    r"(?m)^\.\.\s+(?P<name>[A-Za-z][\w-]*)::"
)

# Section underline characters per Sphinx docs convention.
_SECTION_UNDERLINE_RE = re.compile(r"(?m)^(?P<chars>([=\-~`:'\"^_*+#<>])\2{2,})\s*$")


def load_rst(content: str) -> LoadedDocument:
    """Split RST into prose and code-block segments."""
    if not content:
        return LoadedDocument(text="", segments=(), format_name="rst", warnings=())

    segments: list[FormatSegment] = []
    last = 0
    for match in _CODE_DIRECTIVE_RE.finditer(content):
        if match.start() > last:
            _append_prose(content, last, match.start(), segments)
        directive = match.group(1)
        lang = (match.group("lang") or "").strip()
        segments.append(
            FormatSegment(
                char_start=match.start(),
                char_end=match.end(),
                kind="code",
                metadata={"rst_directive": directive, "rst_language": lang or "text"},
            )
        )
        last = match.end()

    if last < len(content):
        _append_prose(content, last, len(content), segments)

    ordered = tuple(sorted(segments, key=lambda s: s.char_start))
    return LoadedDocument(
        text=content,
        segments=ordered,
        format_name="rst",
        warnings=(),
    )


def _append_prose(
    content: str, start: int, end: int, segments: list[FormatSegment]
) -> None:
    if end <= start:
        return
    text = content[start:end]
    if not text.strip():
        return
    metadata: dict[str, str] = {}
    headings = _extract_section_headings(text)
    if headings:
        metadata["rst_headings"] = "|".join(headings)
    segments.append(
        FormatSegment(
            char_start=start,
            char_end=end,
            kind="prose",
            metadata=metadata,
        )
    )


def _extract_section_headings(prose: str) -> list[str]:
    """Return section titles whose underline appears directly below."""
    lines = prose.splitlines()
    out: list[str] = []
    for idx in range(len(lines) - 1):
        title = lines[idx].strip()
        underline = lines[idx + 1]
        if not title or not underline:
            continue
        if not _SECTION_UNDERLINE_RE.match(underline):
            continue
        if len(underline.strip()) < len(title):
            continue
        out.append(title)
    return out


def detect_rst_directives(content: str) -> list[tuple[str, int]]:
    """Public helper used by tests: list (name, char_offset) for every directive."""
    return [(m.group("name"), m.start()) for m in _GENERIC_DIRECTIVE_RE.finditer(content)]
