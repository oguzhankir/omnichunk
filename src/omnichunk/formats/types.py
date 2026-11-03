from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from omnichunk.types import ByteRange


@dataclass(frozen=True)
class DocumentElement:
    """An extracted element in canonical UTF-8 coordinates, with original references.

    ``metadata`` is JSON-compatible extraction metadata. A missing upstream ID is
    ``None``; coordinates never address the original binary container.
    """

    element_id: str | None
    byte_range: ByteRange
    kind: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FormatSegment:
    """A prose, code or table span using character offsets in canonical text.

    Table metadata contains ``row_ranges``: contiguous canonical UTF-8 byte
    ranges as ``{start, end}`` dictionaries. Ordinary segments need no row map.
    """

    char_start: int
    char_end: int
    kind: Literal["prose", "code", "table"]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedDocument:
    """Canonical extraction text and engine segments, with optional source lineage.

    ``metadata`` extends the source descriptor; ``elements`` are projected onto
    final chunk context after splitting/overlap. Existing loaders leave these
    fields empty. An explicit ChunkOptions source ID overrides ``source_id``.
    """

    text: str
    segments: tuple[FormatSegment, ...]
    format_name: str
    warnings: tuple[str, ...] = ()
    source_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    elements: tuple[DocumentElement, ...] = ()
