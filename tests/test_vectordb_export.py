from __future__ import annotations

import pytest

from omnichunk import Chunker
from omnichunk.serialization import (
    chunks_to_pinecone_vectors,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
)
from omnichunk.types import ByteRange, Chunk, ChunkContext, ContentType, LineRange


def _make_chunks(n: int = 2) -> list[Chunk]:
    out: list[Chunk] = []
    for i in range(n):
        ctx = ChunkContext(
            filepath=f"f{i}.py",
            language="python",
            content_type=ContentType.CODE,
            breadcrumb=["mod", f"fn{i}"],
        )
        out.append(
            Chunk(
                text=f"body{i}",
                contextualized_text=f"ctx{i}",
                byte_range=ByteRange(10 * i, 10 * i + 5),
                line_range=LineRange(i, i + 1),
                index=i,
                total_chunks=n,
                context=ctx,
                token_count=i + 1,
                char_count=5,
                nws_count=3,
            )
        )
    return out


def test_pinecone_vectors_key_structure() -> None:
    chunks = _make_chunks()
    emb = [[0.1, 0.2], [0.3, 0.4]]
    rows = chunks_to_pinecone_vectors(chunks, emb)
    assert len(rows) == 2
    for row, ch, vec in zip(rows, chunks, emb):
        assert set(row) == {"id", "values", "metadata"}
        assert row["values"] == vec
        assert row["metadata"]["filepath"] == ch.context.filepath
        assert row["metadata"]["text"].startswith("ctx")
        assert "byte_start" in row["metadata"]


def test_pinecone_vectors_length_mismatch() -> None:
    with pytest.raises(ValueError, match="embeddings length"):
        chunks_to_pinecone_vectors(_make_chunks(), [[0.0]])


def test_weaviate_objects_structure() -> None:
    chunks = _make_chunks(1)
    emb = [[1.0, 2.0]]
    rows = chunks_to_weaviate_objects(chunks, emb, class_name="Doc")
    assert len(rows) == 1
    r = rows[0]
    assert r["class"] == "Doc"
    assert r["vector"] == [1.0, 2.0]
    assert r["properties"]["language"] == "python"


def test_supabase_rows_content_and_embedding() -> None:
    chunks = _make_chunks(1)
    emb = [[0.5]]
    rows = chunks_to_supabase_rows(chunks, emb, use_contextualized_text=True)
    assert rows[0]["content"] == "ctx0"
    assert rows[0]["embedding"] == [0.5]
    assert rows[0]["filepath"] == "f0.py"


def test_use_contextualized_text_false_uses_raw_text() -> None:
    chunks = _make_chunks(1)
    emb = [[0.0]]
    p = chunks_to_pinecone_vectors(chunks, emb, use_contextualized_text=False)[0]
    w = chunks_to_weaviate_objects(chunks, emb, use_contextualized_text=False)[0]
    s = chunks_to_supabase_rows(chunks, emb, use_contextualized_text=False)[0]
    assert p["metadata"]["text"] == "body0"
    assert w["properties"]["text"] == "body0"
    assert s["content"] == "body0"


def test_pinecone_namespace_omitted_when_empty() -> None:
    rows = chunks_to_pinecone_vectors(_make_chunks(1), [[0.0]], namespace="")
    assert "namespace" not in rows[0]


def test_pinecone_namespace_added_when_set() -> None:
    rows = chunks_to_pinecone_vectors(_make_chunks(1), [[0.0]], namespace="ns1")
    assert rows[0]["namespace"] == "ns1"


def test_chunker_delegates_to_serialization() -> None:
    chunker = Chunker()
    chunks = _make_chunks(1)
    emb = [[1.0, 2.0]]
    assert chunker.to_pinecone_vectors(chunks, emb) == chunks_to_pinecone_vectors(chunks, emb)
    assert chunker.to_weaviate_objects(chunks, emb) == chunks_to_weaviate_objects(chunks, emb)
    assert chunker.to_supabase_rows(chunks, emb) == chunks_to_supabase_rows(chunks, emb)
