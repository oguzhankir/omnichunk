from __future__ import annotations

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from omnichunk.sizing.counter import find_fitting_prefix
from omnichunk.util.text_index import TextIndex


@dataclass(frozen=True)
class ASTNodeWindowItem:
    node: Any | None
    start: int
    end: int
    size: int


@dataclass(frozen=True)
class SourceBudget:
    """Measure canonical byte ranges with the caller's configured unit."""

    text: str
    index: TextIndex
    counter: Callable[[str], int]

    def count(self, start: int, end: int) -> int:
        offsets = self.index._char_to_byte
        left, right = bisect_left(offsets, start), bisect_left(offsets, end)
        if self.counter is len:
            return right - left
        return self.counter(self.text[left:right])

    def fitting_end(self, start: int, end: int, limit: int) -> int:
        offsets = self.index._char_to_byte
        left, right = bisect_left(offsets, start), bisect_left(offsets, end)
        fit = find_fitting_prefix(self.text, left, right, limit, self.counter)
        # Finalization enforces error/preserve when no complete character fits.
        return offsets[fit if fit > left else min(left + 1, right)]
