from __future__ import annotations

from omnichunk import Chunker
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ContentType,
    EntityInfo,
    EntityType,
    LineRange,
)
from omnichunk.windowing.overlap import apply_token_overlap


def test_line_overlap_contextualized_text() -> None:
    code = "def a():\n    return 1\n\ndef b():\n    return 2\n\ndef c():\n    return 3\n"
    chunker = Chunker(max_chunk_size=28, min_chunk_size=8, size_unit="chars", overlap_lines=1)

    chunks = chunker.chunk("example.py", code)

    assert len(chunks) >= 2
    assert any("# ..." in c.contextualized_text for c in chunks[1:])


def test_token_overlap_produces_chunks() -> None:
    code = "\n".join(f"def fn_{i}():\n    return {i}\n" for i in range(12))
    chunker = Chunker(max_chunk_size=80, min_chunk_size=20, size_unit="chars", overlap=0.2)

    chunks = chunker.chunk("many.py", code)

    assert chunks
    assert all(c.total_chunks == len(chunks) for c in chunks)


def test_token_overlap_recomputes_group_context_entities() -> None:
    entity_a = EntityInfo(
        name="alpha",
        type=EntityType.FUNCTION,
        byte_range=ByteRange(1, 8),
        line_range=LineRange(0, 0),
    )
    entity_b = EntityInfo(
        name="beta",
        type=EntityType.FUNCTION,
        byte_range=ByteRange(12, 18),
        line_range=LineRange(1, 1),
    )
    entity_c_partial = EntityInfo(
        name="gamma",
        type=EntityType.CLASS,
        byte_range=ByteRange(18, 26),
        line_range=LineRange(1, 2),
        is_partial=True,
    )

    chunks = [
        Chunk(
            text="a" * 10,
            contextualized_text="a" * 10,
            byte_range=ByteRange(0, 10),
            line_range=LineRange(0, 0),
            index=0,
            total_chunks=3,
            context=ChunkContext(
                language="python",
                content_type=ContentType.CODE,
                entities=[entity_a],
            ),
        ),
        Chunk(
            text="b" * 10,
            contextualized_text="b" * 10,
            byte_range=ByteRange(10, 20),
            line_range=LineRange(1, 1),
            index=1,
            total_chunks=3,
            context=ChunkContext(
                language="python",
                content_type=ContentType.CODE,
                entities=[entity_b, entity_c_partial],
            ),
        ),
        Chunk(
            text="c" * 10,
            contextualized_text="c" * 10,
            byte_range=ByteRange(20, 30),
            line_range=LineRange(2, 2),
            index=2,
            total_chunks=3,
            context=ChunkContext(
                language="python",
                content_type=ContentType.CODE,
                entities=[entity_c_partial],
            ),
        ),
    ]

    merged = apply_token_overlap(chunks, overlap=10, max_chunk_size=30)

    assert merged
    first = merged[0]
    names = {entity.name for entity in first.context.entities}
    assert {"alpha", "beta", "gamma"} <= names

    gamma = next(entity for entity in first.context.entities if entity.name == "gamma")
    assert gamma.is_partial is False


def test_token_overlap_preserves_byte_range_integrity_and_reconstructs() -> None:
    code = (
        "def alpha(x):\n"
        "    return x + 1\n\n"
        "def beta(y):\n"
        "    return y * 2\n\n"
        "def gamma(z):\n"
        "    return z - 3\n"
    )
    chunker = Chunker(max_chunk_size=52, min_chunk_size=18, size_unit="chars", overlap=0.35)
    chunks = chunker.chunk("math_ops.py", code)

    assert chunks

    raw = code.encode("utf-8")
    for chunk in chunks:
        snippet = raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8")
        assert snippet == chunk.text

    reconstructed = bytearray()
    cursor = 0
    for chunk in sorted(chunks, key=lambda item: item.byte_range.start):
        start = chunk.byte_range.start
        end = chunk.byte_range.end
        if end <= cursor:
            continue
        piece_start = max(cursor, start)
        reconstructed.extend(raw[piece_start:end])
        cursor = end

    assert reconstructed.decode("utf-8") == code
