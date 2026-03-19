from __future__ import annotations

from typing import Iterable

import numpy as np

from omnichunk.sizing.nws import get_nws_count

from .models import ASTNodeWindowItem


def split_oversized_leaf(
    item: ASTNodeWindowItem,
    *,
    code: str,
    cumsum: np.ndarray,
    max_size: int,
) -> Iterable[ASTNodeWindowItem]:
    """Split oversized leaf item at line boundaries first, then hard fallback."""
    if item.end <= item.start:
        return []

    text = code.encode("utf-8")
    segment = text[item.start : item.end]
    if not segment:
        return []

    newline_positions = [idx for idx, b in enumerate(segment) if b == 10]
    if newline_positions:
        ranges = _build_ranges_from_newlines(item.start, item.end, newline_positions)
        for start, end in ranges:
            if end <= start:
                continue
            size = get_nws_count(cumsum, start, end)
            if size <= max_size:
                yield ASTNodeWindowItem(node=None, start=start, end=end, size=size)
            else:
                yield from _hard_split(start, end, cumsum, max_size)
        return

    yield from _hard_split(item.start, item.end, cumsum, max_size)


def _build_ranges_from_newlines(start: int, end: int, newline_positions: list[int]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    cursor = start
    for pos in newline_positions:
        boundary = start + pos + 1
        ranges.append((cursor, boundary))
        cursor = boundary
    if cursor < end:
        ranges.append((cursor, end))
    return ranges


def _hard_split(
    start: int,
    end: int,
    cumsum: np.ndarray,
    max_size: int,
) -> Iterable[ASTNodeWindowItem]:
    cursor = start
    while cursor < end:
        low = cursor + 1
        high = end
        best = low
        while low <= high:
            mid = (low + high) // 2
            size = get_nws_count(cumsum, cursor, mid)
            if size <= max_size:
                best = mid
                low = mid + 1
            else:
                high = mid - 1

        if best <= cursor:
            best = min(cursor + 1, end)

        size = get_nws_count(cumsum, cursor, best)
        yield ASTNodeWindowItem(node=None, start=cursor, end=best, size=size)
        cursor = best
