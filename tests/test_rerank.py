from __future__ import annotations

import numpy as np

import omnichunk
from omnichunk.semantic.rerank import rerank_chunks
from omnichunk.types import ByteRange, Chunk, ChunkContext, LineRange


def _chunk(index: int) -> Chunk:
    return Chunk(
        text=f"chunk-{index}",
        contextualized_text=f"chunk-{index}",
        byte_range=ByteRange(0, 1),
        line_range=LineRange(0, 0),
        index=index,
        total_chunks=-1,
        context=ChunkContext(),
    )


# Embeddings chosen so similarity to query=[1,0] is: c0=1.0, c1=0.8, c2=0.0.
_QUERY = np.array([1.0, 0.0])
_EMB = np.array([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]])
_CHUNKS = [_chunk(0), _chunk(1), _chunk(2)]


def _order(result: list[Chunk]) -> list[int]:
    return [c.index for c in result]


def test_pure_relevance_lambda_one() -> None:
    out = rerank_chunks(_QUERY, _EMB, _CHUNKS, top_k=3, lambda_=1.0)
    # Ranked strictly by query similarity: c0 (1.0) > c1 (0.8) > c2 (0.0).
    assert _order(out) == [0, 1, 2]


def test_pure_diversity_lambda_zero() -> None:
    out = rerank_chunks(_QUERY, _EMB, _CHUNKS, top_k=3, lambda_=0.0)
    # First = most relevant (c0). Then most diverse: c2 (orthogonal) before c1.
    assert _order(out) == [0, 2, 1]


def test_top_k_limits_results() -> None:
    out = rerank_chunks(_QUERY, _EMB, _CHUNKS, top_k=2, lambda_=1.0)
    assert len(out) == 2
    assert _order(out) == [0, 1]


def test_returns_chunk_objects_from_input() -> None:
    out = rerank_chunks(_QUERY, _EMB, _CHUNKS, top_k=3, lambda_=0.5)
    assert all(isinstance(c, Chunk) for c in out)
    assert set(_order(out)) == {0, 1, 2}


def test_accessible_from_top_level() -> None:
    assert omnichunk.rerank_chunks is rerank_chunks
    out = omnichunk.rerank_chunks(_QUERY, _EMB, _CHUNKS, top_k=1)
    assert _order(out) == [0]


def test_empty_chunks_returns_empty() -> None:
    assert rerank_chunks(_QUERY, np.zeros((0, 2)), [], top_k=5) == []


def test_lower_lambda_promotes_diversity() -> None:
    # c0..c2 are near-duplicate relevant chunks; c3 is diverse but less relevant.
    query = np.array([1.0, 0.0])
    emb = np.array([[1.0, 0.0], [0.95, 0.31], [0.9, 0.44], [0.3, 0.95]])
    chunks = [_chunk(i) for i in range(4)]

    relevance = rerank_chunks(query, emb, chunks, top_k=4, lambda_=1.0)
    diversity = rerank_chunks(query, emb, chunks, top_k=4, lambda_=0.0)

    # Pure relevance ranks the diverse chunk last; diversity pulls it forward.
    assert _order(relevance).index(3) > _order(diversity).index(3)
    assert _order(diversity)[1] == 3
