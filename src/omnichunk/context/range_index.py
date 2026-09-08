"""Sweep entities once for chunks emitted in source order."""

from __future__ import annotations

from heapq import heappop, heappush

from omnichunk.types import ByteRange, EntityInfo


class EntityRangeSweep:
    """O(E log E + C + K) overlap lookup for monotonic source ranges.

    E is the entity count, C the chunk count, and K the emitted entity references.
    Long enclosing definitions stay active while completed siblings are discarded.
    """

    def __init__(self, entities: list[EntityInfo]) -> None:
        self._rows = sorted(
            [
                (e.byte_range.start, e.byte_range.end, i, e)
                for i, e in enumerate(entities)
                if e.byte_range is not None
            ],
            key=lambda row: (row[0], row[2]),
        )
        self._position = 0
        self._active: dict[int, EntityInfo] = {}
        self._ends: list[tuple[int, int]] = []
        self._previous = ByteRange(0, 0)

    def overlapping(self, span: ByteRange) -> list[EntityInfo]:
        if span.start < self._previous.start or span.end < self._previous.end:
            raise ValueError("EntityRangeSweep requires ranges in source order")
        self._previous = span
        while self._position < len(self._rows):
            start, end, index, entity = self._rows[self._position]
            if start >= span.end:
                break
            self._position += 1
            if end > span.start:
                self._active[index] = entity
                heappush(self._ends, (end, index))
        while self._ends and self._ends[0][0] <= span.start:
            _, index = heappop(self._ends)
            self._active.pop(index, None)
        return list(self._active.values())
