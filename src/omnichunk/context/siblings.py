from __future__ import annotations

from omnichunk.types import ByteRange, EntityInfo, EntityType, SiblingInfo


def detect_siblings_for_chunk(
    entities: list[EntityInfo],
    chunk_range: ByteRange,
    *,
    max_siblings: int = 3,
) -> list[SiblingInfo]:
    """Detect neighboring entities around a chunk, ordered by distance."""
    all_entities = [
        e
        for e in entities
        if e.byte_range is not None and e.type not in {EntityType.IMPORT, EntityType.EXPORT}
    ]
    all_entities.sort(key=lambda e: e.byte_range.start if e.byte_range else 0)

    if not all_entities:
        return []

    scoped_entities = _scope_local_entities(all_entities, chunk_range)

    overlapping = [e for e in scoped_entities if _overlaps(e.byte_range, chunk_range)]
    if not overlapping:
        anchor_idx = _nearest_index(scoped_entities, chunk_range.start)
    else:
        first = min(overlapping, key=lambda e: e.byte_range.start if e.byte_range else 0)
        anchor_idx = scoped_entities.index(first)

    siblings: list[SiblingInfo] = []

    before_count = 0
    idx = anchor_idx - 1
    while idx >= 0 and before_count < max_siblings:
        ent = scoped_entities[idx]
        if not _overlaps(ent.byte_range, chunk_range):
            siblings.append(
                SiblingInfo(
                    name=ent.name,
                    type=ent.type,
                    position="before",
                    distance=before_count + 1,
                    signature=ent.signature,
                )
            )
            before_count += 1
        idx -= 1

    after_count = 0
    idx = anchor_idx + 1
    while idx < len(scoped_entities) and after_count < max_siblings:
        ent = scoped_entities[idx]
        if not _overlaps(ent.byte_range, chunk_range):
            siblings.append(
                SiblingInfo(
                    name=ent.name,
                    type=ent.type,
                    position="after",
                    distance=after_count + 1,
                    signature=ent.signature,
                )
            )
            after_count += 1
        idx += 1

    siblings.sort(key=lambda s: (0 if s.position == "before" else 1, s.distance))
    return siblings


def _scope_local_entities(entities: list[EntityInfo], chunk_range: ByteRange) -> list[EntityInfo]:
    overlapping = [e for e in entities if _overlaps(e.byte_range, chunk_range)]

    anchor: EntityInfo | None = None
    if overlapping:
        anchor = min(overlapping, key=lambda e: e.byte_range.start if e.byte_range else 0)
    else:
        nearest_idx = _nearest_index(entities, chunk_range.start)
        if 0 <= nearest_idx < len(entities):
            anchor = entities[nearest_idx]

    if anchor is None or not anchor.parent:
        return entities

    local = [e for e in entities if e.parent == anchor.parent]
    if len(local) < 2:
        return entities

    local.sort(key=lambda e: e.byte_range.start if e.byte_range else 0)
    return local


def _overlaps(a: ByteRange | None, b: ByteRange) -> bool:
    if a is None:
        return False
    return not (a.end <= b.start or a.start >= b.end)


def _nearest_index(entities: list[EntityInfo], target_start: int) -> int:
    if not entities:
        return 0
    nearest_idx = 0
    nearest_dist = float("inf")
    for idx, entity in enumerate(entities):
        if entity.byte_range is None:
            continue
        dist = abs(entity.byte_range.start - target_start)
        if dist < nearest_dist:
            nearest_idx = idx
            nearest_dist = dist
    return nearest_idx
