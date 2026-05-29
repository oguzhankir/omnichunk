"""Maximal Marginal Relevance (MMR) reranking of retrieved chunks.

MMR balances relevance to a query against diversity among the selected
results, reducing near-duplicate hits in RAG retrieval. Selection is greedy
and vectorized: each round scores remaining candidates against the query and
their maximum similarity to the already-selected set, costing O(N * top_k).
"""

from __future__ import annotations

from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from omnichunk.types import Chunk


def _l2_normalize(matrix: NDArray[Any]) -> NDArray[Any]:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return cast("NDArray[Any]", matrix / norms)


def rerank_chunks(
    query_embedding: NDArray[Any],
    chunk_embeddings: NDArray[Any],
    chunks: list[Chunk],
    *,
    top_k: int = 10,
    lambda_: float = 0.5,
) -> list[Chunk]:
    """Return up to ``top_k`` chunks reranked by Maximal Marginal Relevance.

    ``lambda_`` trades relevance for diversity:

    - ``lambda_ == 1.0`` -> pure relevance (chunks ranked by cosine similarity
      to the query).
    - ``lambda_ == 0.0`` -> pure diversity (after the single most relevant
      chunk, each pick is the one least similar to those already chosen).

    ``query_embedding`` is a 1D vector of dimension ``D``; ``chunk_embeddings``
    is ``(N, D)`` aligned with ``chunks``. Cosine similarity is used throughout,
    so inputs need not be pre-normalized. Selection is deterministic (ties
    broken by the smaller chunk index).
    """
    n = len(chunks)
    if n == 0 or top_k <= 0:
        return []
    emb = np.asarray(chunk_embeddings, dtype=np.float64)
    if emb.ndim != 2 or emb.shape[0] != n:
        raise ValueError(
            f"chunk_embeddings must be 2D with shape ({n}, D), got {emb.shape}"
        )
    query = np.asarray(query_embedding, dtype=np.float64).reshape(-1)

    normalized = _l2_normalize(emb)
    q_norm = query / (np.linalg.norm(query) or 1.0)
    query_sim = normalized @ q_norm  # (N,)

    lam = float(lambda_)
    k = min(int(top_k), n)

    # First selection: the most query-relevant chunk (independent of lambda).
    first = int(np.argmax(query_sim))
    selected = [first]
    remaining = [i for i in range(n) if i != first]
    max_sim_to_selected = normalized @ normalized[first]  # (N,)

    while remaining and len(selected) < k:
        mmr = lam * query_sim - (1.0 - lam) * max_sim_to_selected
        # Deterministic argmax over remaining: highest score, then smallest index.
        best = max(remaining, key=lambda i: (float(mmr[i]), -i))
        selected.append(best)
        remaining.remove(best)
        sims_to_best = normalized @ normalized[best]
        max_sim_to_selected = np.maximum(max_sim_to_selected, sims_to_best)

    return [chunks[i] for i in selected]
