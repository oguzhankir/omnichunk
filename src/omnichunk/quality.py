from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from omnichunk.types import Chunk, ChunkQualityScore, ChunkStats

SizeUnit = Literal["tokens", "chars", "nws"]


def compute_chunk_quality_scores(
    chunks: Sequence[Chunk],
    *,
    min_chunk_size: int,
    max_chunk_size: int,
    size_unit: str,
) -> list[ChunkQualityScore]:
    """Compute deterministic quality scores for each chunk."""
    if not chunks:
        return []

    lower = max(1, int(min_chunk_size))
    upper = max(lower, int(max_chunk_size))
    unit = _normalize_size_unit(size_unit)

    out: list[ChunkQualityScore] = []
    for chunk in chunks:
        size_value = _chunk_size_value(chunk, unit)
        entity_integrity = _entity_integrity(chunk)
        scope_consistency = _scope_consistency(chunk)
        size_balance = _size_balance(size_value=size_value, min_size=lower, max_size=upper)

        overall = (entity_integrity * 0.45) + (scope_consistency * 0.3) + (size_balance * 0.25)
        out.append(
            ChunkQualityScore(
                index=chunk.index,
                overall=round(_clamp01(overall), 4),
                entity_integrity=round(entity_integrity, 4),
                scope_consistency=round(scope_consistency, 4),
                size_balance=round(size_balance, 4),
                size_value=size_value,
            )
        )

    return out


def compute_chunk_stats(chunks: Sequence[Chunk], *, size_unit: str) -> ChunkStats:
    """Compute aggregate deterministic stats for chunk collections."""
    unit = _normalize_size_unit(size_unit)
    if not chunks:
        return ChunkStats(
            total_chunks=0,
            average_size=0.0,
            min_size=0,
            max_size=0,
            size_unit=unit,
            entity_distribution={},
        )

    sizes = [_chunk_size_value(chunk, unit) for chunk in chunks]
    average = sum(sizes) / len(sizes)

    entity_distribution: dict[str, int] = {}
    for chunk in chunks:
        for entity in chunk.context.entities:
            key = entity.type.value
            entity_distribution[key] = entity_distribution.get(key, 0) + 1

    return ChunkStats(
        total_chunks=len(chunks),
        average_size=round(average, 4),
        min_size=min(sizes),
        max_size=max(sizes),
        size_unit=unit,
        entity_distribution=dict(sorted(entity_distribution.items())),
    )


def _entity_integrity(chunk: Chunk) -> float:
    entities = list(chunk.context.entities)
    if not entities:
        return 1.0

    partial_count = sum(1 for entity in entities if entity.is_partial)
    score = 1.0 - (partial_count / len(entities))
    return _clamp01(score)


def _scope_consistency(chunk: Chunk) -> float:
    scope_labels: set[str] = set()

    if chunk.context.breadcrumb:
        scope_labels.add("::".join(chunk.context.breadcrumb))

    for entity in chunk.context.entities:
        if entity.parent:
            scope_labels.add(entity.parent)
        elif entity.name:
            scope_labels.add(entity.name)

    if not scope_labels:
        return 1.0

    distinct = len(scope_labels)
    if distinct <= 1:
        return 1.0
    if distinct == 2:
        return 0.75

    penalty = 0.22 * (distinct - 2)
    return _clamp01(0.75 - penalty)


def _size_balance(*, size_value: int, min_size: int, max_size: int) -> float:
    if max_size <= min_size:
        return 1.0

    if size_value <= min_size or size_value >= max_size:
        return 0.0

    midpoint = (min_size + max_size) / 2
    half_span = (max_size - min_size) / 2
    if half_span <= 0:
        return 1.0

    distance = abs(size_value - midpoint)
    score = 1.0 - (distance / half_span)
    return _clamp01(score)


def _chunk_size_value(chunk: Chunk, size_unit: str) -> int:
    if size_unit == "tokens":
        return int(chunk.token_count)
    if size_unit == "nws":
        return int(chunk.nws_count)
    return int(chunk.char_count)


def _normalize_size_unit(size_unit: str) -> SizeUnit:
    if size_unit in {"tokens", "chars", "nws"}:
        return cast(SizeUnit, size_unit)
    return "chars"


def _clamp01(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value
