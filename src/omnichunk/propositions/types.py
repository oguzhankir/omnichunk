from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from omnichunk.types import ByteRange


@dataclass(frozen=True)
class Proposition:
    """A short, self-contained factual claim extracted from a document."""

    text: str
    byte_range: ByteRange
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)
