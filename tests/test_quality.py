from __future__ import annotations

from omnichunk.quality import compute_chunk_quality_scores, compute_chunk_stats
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    EntityInfo,
    EntityType,
    LineRange,
)


def test_quality_scores_penalize_partial_entities_and_size_extremes() -> None:
    clean_chunk = Chunk(
        text="def clean():\n    return 1\n",
        contextualized_text="def clean():\n    return 1\n",
        byte_range=ByteRange(0, 24),
        line_range=LineRange(0, 1),
        index=0,
        total_chunks=2,
        context=ChunkContext(
            filepath="sample.py",
            language="python",
            entities=[
                EntityInfo(
                    name="clean",
                    type=EntityType.FUNCTION,
                    byte_range=ByteRange(0, 24),
                    line_range=LineRange(0, 1),
                )
            ],
            breadcrumb=["clean"],
        ),
        token_count=7,
        char_count=24,
        nws_count=19,
    )

    partial_chunk = Chunk(
        text="return a + b",
        contextualized_text="return a + b",
        byte_range=ByteRange(24, 36),
        line_range=LineRange(2, 2),
        index=1,
        total_chunks=2,
        context=ChunkContext(
            filepath="sample.py",
            language="python",
            entities=[
                EntityInfo(
                    name="calc",
                    type=EntityType.FUNCTION,
                    byte_range=ByteRange(10, 48),
                    line_range=LineRange(0, 3),
                    is_partial=True,
                )
            ],
            breadcrumb=["calc", "nested"],
        ),
        token_count=4,
        char_count=12,
        nws_count=9,
    )

    scores = compute_chunk_quality_scores(
        [clean_chunk, partial_chunk],
        min_chunk_size=12,
        max_chunk_size=36,
        size_unit="chars",
    )

    assert len(scores) == 2
    assert scores[0].overall > scores[1].overall
    assert scores[0].entity_integrity == 1.0
    assert scores[1].entity_integrity < 1.0


def test_chunk_stats_aggregate_size_and_entity_distribution() -> None:
    chunks = [
        Chunk(
            text="a",
            contextualized_text="a",
            byte_range=ByteRange(0, 1),
            line_range=LineRange(0, 0),
            index=0,
            total_chunks=2,
            context=ChunkContext(
                filepath="x.py",
                language="python",
                entities=[EntityInfo(name="x", type=EntityType.FUNCTION)],
            ),
            token_count=1,
            char_count=1,
            nws_count=1,
        ),
        Chunk(
            text="bc",
            contextualized_text="bc",
            byte_range=ByteRange(1, 3),
            line_range=LineRange(1, 1),
            index=1,
            total_chunks=2,
            context=ChunkContext(
                filepath="x.py",
                language="python",
                entities=[EntityInfo(name="Y", type=EntityType.CLASS)],
            ),
            token_count=2,
            char_count=2,
            nws_count=2,
        ),
    ]

    stats = compute_chunk_stats(chunks, size_unit="chars")

    assert stats.total_chunks == 2
    assert stats.average_size == 1.5
    assert stats.min_size == 1
    assert stats.max_size == 2
    assert stats.entity_distribution == {"class": 1, "function": 1}
