from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from omnichunk.sizing.rust_accel import batch_cosine_similarity_adjacent_rust


@dataclass(frozen=True)
class SemanticBoundaryResult:
    """Result of semantic boundary detection."""

    boundary_indices: tuple[int, ...]
    """Sorted sentence indices after which a boundary is placed.
    Boundary at index i means: sentences[:i+1] go in one chunk,
    sentences[i+1:] start the next chunk."""
    similarity_scores: tuple[float, ...]
    """Cosine similarity between adjacent window embeddings.
    len(similarity_scores) == len(sentences) - 1."""


def _batch_cosine_similarity(
    embeddings: np.ndarray,
) -> np.ndarray:
    """Adjacent cosine similarities. Tries Rust backend; falls back to numpy."""
    rust_result = batch_cosine_similarity_adjacent_rust(embeddings)
    if rust_result is not None:
        return rust_result
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normalized = embeddings / norms
    return np.einsum("id,id->i", normalized[:-1], normalized[1:])


def detect_semantic_boundaries(
    sentences: Sequence[str],
    *,
    embed_fn: Callable[[list[str]], np.ndarray],
    window: int = 3,
    threshold: float = 0.3,
    min_chunk_sentences: int = 1,
) -> SemanticBoundaryResult:
    """Detect semantic boundaries via sliding-window cosine similarity."""
    if window < 1:
        raise ValueError("window must be >= 1")
    n = len(sentences)
    if n == 0:
        return SemanticBoundaryResult((), ())
    w = int(window)
    windows: list[str] = []
    half = w // 2
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        windows.append("".join(sentences[lo:hi]))

    arr = np.asarray(embed_fn(windows))
    if arr.ndim != 2 or arr.shape[0] != n:
        raise ValueError(
            f"embed_fn must return 2D array with shape ({n}, D), got {arr.shape}"
        )
    if n == 1:
        return SemanticBoundaryResult((), ())

    sims = np.asarray(_batch_cosine_similarity(arr), dtype=np.float64)
    sims_tuple = tuple(float(x) for x in sims.tolist())

    last_boundary = -1
    boundaries: list[int] = []
    for k in range(len(sims)):
        is_valley = (
            0 < k < len(sims) - 1
            and sims[k] < sims[k - 1]
            and sims[k] < sims[k + 1]
        )
        is_low = sims[k] < threshold
        span = k - last_boundary
        if (is_low or is_valley) and span >= min_chunk_sentences:
            boundaries.append(k)
            last_boundary = k

    return SemanticBoundaryResult(tuple(boundaries), sims_tuple)
