from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class FormatSegment:
    """A prose or code span within a canonical UTF-8 document string."""

    char_start: int
    char_end: int
    kind: Literal["prose", "code"]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedDocument:
    """Result of parsing a structured file into linear text plus engine segments."""

    text: str
    segments: tuple[FormatSegment, ...]
    format_name: str
    warnings: tuple[str, ...] = ()
