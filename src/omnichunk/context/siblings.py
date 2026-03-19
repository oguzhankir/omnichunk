from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass

from omnichunk.types import ByteRange, EntityInfo, SiblingInfo

_IGNORED_ENTITY_TYPES = {"import", "export"}


@dataclass(frozen=True)
class _SiblingRow:
    entity: EntityInfo
    start: int
    end: int


@dataclass(frozen=True)
class _ParentGroup:
    rows: tuple[_SiblingRow, ...]
    global_to_local: dict[int, int]


@dataclass(frozen=True)
class SiblingIndex:
    rows: tuple[_SiblingRow, ...]
    starts: tuple[int, ...]
    prefix_max_ends: tuple[int, ...]
    parent_groups: dict[str, _ParentGroup]


def build_sibling_index(entities: list[EntityInfo]) -> SiblingIndex:
    rows: list[_SiblingRow] = []
    for entity in entities:
        byte_range = entity.byte_range
        if byte_range is None:
            continue
        if entity.type.value in _IGNORED_ENTITY_TYPES:
            continue
        rows.append(
            _SiblingRow(
                entity=entity,
                start=int(byte_range.start),
                end=int(byte_range.end),
            )
        )

    rows.sort(key=lambda row: (row.start, row.end, row.entity.name))
    sorted_rows = tuple(rows)
    starts = tuple(row.start for row in sorted_rows)
    prefix_max_ends = _build_prefix_max_ends(sorted_rows)
    parent_groups = _build_parent_groups(sorted_rows)

    return SiblingIndex(
        rows=sorted_rows,
        starts=starts,
        prefix_max_ends=prefix_max_ends,
        parent_groups=parent_groups,
    )


def detect_siblings_for_chunk(
    entities: list[EntityInfo] | SiblingIndex,
    chunk_range: ByteRange,
    *,
    max_siblings: int = 3,
) -> list[SiblingInfo]:
    """Detect neighboring entities around a chunk, ordered by distance."""
    if max_siblings <= 0:
        return []

    sibling_index = (
        entities if isinstance(entities, SiblingIndex) else build_sibling_index(entities)
    )
    if not sibling_index.rows:
        return []

    anchor_global_idx = _resolve_anchor_index(sibling_index, chunk_range)

    active_rows = sibling_index.rows
    anchor_local_idx = anchor_global_idx

    anchor_parent = active_rows[anchor_global_idx].entity.parent
    if anchor_parent:
        group = sibling_index.parent_groups.get(anchor_parent)
        if group is not None:
            active_rows = group.rows
            anchor_local_idx = group.global_to_local.get(anchor_global_idx, anchor_local_idx)

    before = _collect_directional_siblings(
        active_rows,
        chunk_range,
        anchor_local_idx,
        direction=-1,
        max_siblings=max_siblings,
    )
    after = _collect_directional_siblings(
        active_rows,
        chunk_range,
        anchor_local_idx,
        direction=1,
        max_siblings=max_siblings,
    )

    return before + after


def _build_prefix_max_ends(rows: tuple[_SiblingRow, ...]) -> tuple[int, ...]:
    prefix: list[int] = []
    running = -1
    for row in rows:
        if row.end > running:
            running = row.end
        prefix.append(running)
    return tuple(prefix)


def _build_parent_groups(rows: tuple[_SiblingRow, ...]) -> dict[str, _ParentGroup]:
    grouped: dict[str, list[tuple[int, _SiblingRow]]] = {}
    for global_idx, row in enumerate(rows):
        parent = row.entity.parent
        if not parent:
            continue
        grouped.setdefault(parent, []).append((global_idx, row))

    out: dict[str, _ParentGroup] = {}
    for parent, items in grouped.items():
        if len(items) < 2:
            continue
        parent_rows = tuple(row for _, row in items)
        global_to_local = {global_idx: local_idx for local_idx, (global_idx, _) in enumerate(items)}
        out[parent] = _ParentGroup(rows=parent_rows, global_to_local=global_to_local)
    return out


def _resolve_anchor_index(sibling_index: SiblingIndex, chunk_range: ByteRange) -> int:
    overlap_idx = _find_first_overlap_index(sibling_index, chunk_range)
    if overlap_idx >= 0:
        return overlap_idx
    return _nearest_index_by_start(sibling_index.starts, chunk_range.start)


def _find_first_overlap_index(sibling_index: SiblingIndex, chunk_range: ByteRange) -> int:
    right = bisect_left(sibling_index.starts, chunk_range.end)
    if right <= 0:
        return -1

    left = bisect_left(sibling_index.prefix_max_ends, chunk_range.start + 1, hi=right)
    for idx in range(left, right):
        row = sibling_index.rows[idx]
        if _ranges_overlap(row.start, row.end, chunk_range.start, chunk_range.end):
            return idx
    return -1


def _nearest_index_by_start(starts: tuple[int, ...], target_start: int) -> int:
    if not starts:
        return 0

    idx = bisect_left(starts, target_start)
    if idx <= 0:
        return 0
    if idx >= len(starts):
        return len(starts) - 1

    prev_idx = idx - 1
    prev_dist = abs(starts[prev_idx] - target_start)
    curr_dist = abs(starts[idx] - target_start)
    if curr_dist < prev_dist:
        return idx
    return prev_idx


def _collect_directional_siblings(
    rows: tuple[_SiblingRow, ...],
    chunk_range: ByteRange,
    anchor_idx: int,
    *,
    direction: int,
    max_siblings: int,
) -> list[SiblingInfo]:
    siblings: list[SiblingInfo] = []
    distance = 0

    idx = anchor_idx + direction
    while 0 <= idx < len(rows) and distance < max_siblings:
        row = rows[idx]
        if not _ranges_overlap(row.start, row.end, chunk_range.start, chunk_range.end):
            distance += 1
            siblings.append(
                SiblingInfo(
                    name=row.entity.name,
                    type=row.entity.type,
                    position="before" if direction < 0 else "after",
                    distance=distance,
                    signature=row.entity.signature,
                )
            )

        idx += direction

    return siblings


def _ranges_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return not (a_end <= b_start or a_start >= b_end)
