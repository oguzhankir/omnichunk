from __future__ import annotations

from array import array
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import accumulate
from typing import Any

from omnichunk.sizing.counter import find_fitting_prefix
from omnichunk.util.text_index import TextIndex


def _incremental_fitting_prefix(
    text: str, start: int, end: int, limit: int, count: Callable[[str], int]
) -> int:
    """Bracket a verified prefix without repeatedly measuring the whole suffix.

    Counters need not be additive or monotone. Geometric probes choose only a
    search bracket; the returned prefix is still measured independently. Keep
    full-range recovery when the bracket has no fitting prefix, since completing
    a later token can lower a custom counter's result. Neither this bracketing
    nor binary probing promises the globally longest fit for arbitrary counters.
    """
    width = max(1, limit)
    while True:
        probe = min(end, start + width)
        if count(text[start:probe]) > limit:
            break
        if probe == end:
            return end
        width *= 2
    fit = find_fitting_prefix(text, start, probe, limit, count)
    if fit == start and probe < end:
        return find_fitting_prefix(text, start, end, limit, count)
    return fit


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

    def fitting_end(self, start: int, end: int, limit: int, *, incremental: bool = False) -> int:
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
            search = (
                _incremental_fitting_prefix
                if incremental and self.counter is not len
                else find_fitting_prefix
            )
            fit = search(self.text, left, right, limit, self.counter)
        # Finalization enforces error/preserve when no complete character fits.
        return offsets[fit if fit > left else min(left + 1, right)]
