from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import accumulate
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
    size_unit: str = "tokens"
    _nws_prefix: Sequence[int] | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if self.size_unit == "nws":
            # The byte-based legacy NWS index cannot count Unicode characters
            # or Unicode whitespace. Build this character index once, avoiding
            # repeated scans of shrinking suffixes during oversized-leaf splits.
            object.__setattr__(
                self,
                "_nws_prefix",
                array("Q", accumulate((not char.isspace() for char in self.text), initial=0)),
            )

    def count(self, start: int, end: int) -> int:
        offsets = self.index._char_to_byte
        left, right = bisect_left(offsets, start), bisect_left(offsets, end)
        if self._nws_prefix is not None:
            return self._nws_prefix[right] - self._nws_prefix[left]
        if self.counter is len:
            return right - left
        return self.counter(self.text[left:right])

    def fitting_end(self, start: int, end: int, limit: int) -> int:
        offsets = self.index._char_to_byte
        left, right = bisect_left(offsets, start), bisect_left(offsets, end)
        if self._nws_prefix is not None:
            fit = (
                bisect_right(
                    self._nws_prefix, self._nws_prefix[left] + limit, lo=left, hi=right + 1
                )
                - 1
            )
        else:
            fit = find_fitting_prefix(self.text, left, right, limit, self.counter)
        # Finalization enforces error/preserve when no complete character fits.
        return offsets[fit if fit > left else min(left + 1, right)]
