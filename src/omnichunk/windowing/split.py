from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from omnichunk.sizing.nws import get_nws_count

from .models import ASTNodeWindowItem

_SAFE_BOUNDARY_BYTES = {9, 10, 11, 12, 13, 32, 44, 59, 41, 93, 125}

_OPEN_TO_CLOSE: dict[int, int] = {40: 41, 91: 93, 123: 125}


def find_statement_boundary(
    source_bytes: bytes,
    start: int,
    candidate_end: int,
    hard_end: int,
) -> int:
    """Largest split end in ``(start, min(candidate_end, hard_end)]`` at a statement-like boundary.

    Depth must be zero and strings closed. After ``\\n``, split if the prior line ends with ``;``
    or the next line starts at column 0. If none match, returns ``candidate_end``.
    """
    end_cap = min(candidate_end, hard_end)
    if end_cap <= start + 1:
        return candidate_end

    n = len(source_bytes)
    best_stmt = -1
    stack: list[int] = []
    line_start = start
    in_string: str | None = None
    escape = False
    idx = start

    while idx < end_cap:
        b = source_bytes[idx]

        if in_string is not None:
            if escape:
                escape = False
                idx += 1
                continue
            if b == 92:  # backslash
                escape = True
                idx += 1
                continue
            if in_string == "ddd":
                if idx + 2 < n and source_bytes[idx : idx + 3] == b'"""':
                    in_string = None
                    idx += 3
                else:
                    idx += 1
                continue
            if in_string == "sss":
                if idx + 2 < n and source_bytes[idx : idx + 3] == b"'''":
                    in_string = None
                    idx += 3
                else:
                    idx += 1
                continue
            if (in_string == "d" and b == 34) or (in_string == "s" and b == 39):
                in_string = None
            idx += 1
            continue

        if b == 35:  # '#' line comment
            idx += 1
            while idx < n and source_bytes[idx] != 10:
                idx += 1
            continue

        if b == 10:
            nl = idx
            idx += 1
            if idx <= end_cap and not stack and in_string is None:
                prev = source_bytes[line_start:nl]
                if _line_bytes_end_with_semicolon(prev) or (
                    idx < n and source_bytes[idx] not in (9, 32, 10)
                ):
                    best_stmt = idx
            line_start = idx
            continue

        if b == 34:  # "
            if idx + 2 < n and source_bytes[idx : idx + 3] == b'"""':
                in_string = "ddd"
                idx += 3
            else:
                in_string = "d"
                idx += 1
            continue

        if b == 39:  # '
            if idx + 2 < n and source_bytes[idx : idx + 3] == b"'''":
                in_string = "sss"
                idx += 3
            else:
                in_string = "s"
                idx += 1
            continue

        close_expect = _OPEN_TO_CLOSE.get(b)
        if close_expect is not None:
            stack.append(close_expect)
            idx += 1
            continue

        if b in (41, 93, 125):
            if stack and stack[-1] == b:
                stack.pop()
            idx += 1
            continue

        idx += 1

    if best_stmt <= start:
        return candidate_end
    return best_stmt


def _line_bytes_end_with_semicolon(line: bytes) -> bool:
    i = len(line)
    while i > 0 and line[i - 1] in (9, 32, 11, 12, 13):
        i -= 1
    return i > 0 and line[i - 1] == 59


def split_oversized_leaf(
    item: ASTNodeWindowItem,
    *,
    code: str,
    cumsum: np.ndarray,
    max_size: int,
) -> Iterable[ASTNodeWindowItem]:
    """Split oversized leaf item at line boundaries first, then safe-boundary fallback."""
    if item.end <= item.start:
        return

    text = code.encode("utf-8")
    segment = text[item.start : item.end]
    if not segment:
        return

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
                yield from _hard_split(start, end, cumsum, max_size, text)
        return

    yield from _hard_split(item.start, item.end, cumsum, max_size, text)


def _build_ranges_from_newlines(
    start: int, end: int, newline_positions: list[int]
) -> list[tuple[int, int]]:
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
    source_bytes: bytes,
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

        best = find_statement_boundary(source_bytes, cursor, best, end)
        best = _adjust_to_safe_boundary(source_bytes, cursor, best, end)
        if best <= cursor:
            best = min(cursor + 1, end)

        size = get_nws_count(cumsum, cursor, best)
        yield ASTNodeWindowItem(node=None, start=cursor, end=best, size=size)
        cursor = best


def _adjust_to_safe_boundary(
    source_bytes: bytes,
    start: int,
    candidate_end: int,
    hard_end: int,
) -> int:
    if candidate_end <= start + 1:
        return candidate_end

    upper = min(candidate_end, hard_end)
    for idx in range(upper - 1, start, -1):
        if source_bytes[idx] in _SAFE_BOUNDARY_BYTES:
            return idx + 1

    return candidate_end
