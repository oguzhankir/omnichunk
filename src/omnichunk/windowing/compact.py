"""Optional measured packing of oversized code, with fitting definitions protected."""

from __future__ import annotations

from bisect import bisect_right

from .models import SourceBudget


def compact_code_ranges(
    structural: list[tuple[int, int]],
    *,
    budget: SourceBudget,
    max_size: int,
    protected: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Prefer fewer fragments, then fuller earlier measured payloads.

    Alternative layouts may divide expressions in oversized declarations, but
    never divide a fitting protected definition or documented root group.
    Every candidate is measured independently; token additivity is not assumed.
    """
    if len(structural) < 2:
        return structural
    raw = budget.index.raw_bytes
    total = len(raw)
    whole_size = budget.count(0, total)
    minimum_fragments = max(1, (whole_size + max_size - 1) // max_size)
    balanced_target = max(1, (whole_size + minimum_fragments - 1) // minimum_fragments)
    newline_ends = [index + 1 for index, byte in enumerate(raw) if byte == 10]

    # Keep outer fitting groups; nested definitions add no further constraint.
    units: list[tuple[int, int]] = []
    for start, end in sorted(set(protected), key=lambda item: (item[0], -item[1])):
        if units and start < units[-1][1]:
            if end <= units[-1][1]:
                continue
            # Crossing, non-nested protections are not a valid alternative layout.
            return structural
        units.append((start, end))
    unit_starts = [left for left, _ in units]

    def containing(end: int) -> tuple[int, int] | None:
        position = bisect_right(unit_starts, end) - 1
        if position >= 0:
            left, right = units[position]
            if left < end < right:
                return left, right
        return None

    def permitted_cut(start: int, end: int) -> int | None:
        unit = containing(end)
        if unit is not None:
            left, right = unit
            if start <= left and budget.count(start, right) <= max_size:
                return right
            if start < left and budget.count(start, left) <= max_size:
                return left
            return None
        return end

    def layout(target: int, prefer_lines: bool) -> list[tuple[int, int]] | None:
        ranges: list[tuple[int, int]] = []
        cursor = 0
        while cursor < total:
            end = permitted_cut(cursor, budget.fitting_end(cursor, total, target))
            if end is None or end <= cursor or budget.count(cursor, end) > max_size:
                return None
            if prefer_lines and end < total:
                position = bisect_right(newline_ends, end) - 1
                while position >= 0 and newline_ends[position] > cursor:
                    candidate = newline_ends[position]
                    measured = budget.count(cursor, candidate)
                    if measured < 0.75 * target:
                        break
                    if measured <= max_size and containing(candidate) is None:
                        end = candidate
                        break
                    position -= 1
            ranges.append((cursor, end))
            cursor = end
        return ranges

    candidates = (
        [structural]
        if all(
            budget.count(start, end) <= max_size and containing(end) is None
            for start, end in structural
        )
        else []
    )
    for target, prefer_lines in [(max_size, False), (max_size, True), (balanced_target, False)]:
        candidate = layout(target, prefer_lines)
        if candidate is not None:
            candidates.append(candidate)

    def key(ranges: list[tuple[int, int]]) -> tuple[int, tuple[int, ...]]:
        sizes = [budget.count(start, end) for start, end in ranges]
        return len(ranges), tuple(-size for size in sizes)

    return min(candidates, key=key) if candidates else structural
