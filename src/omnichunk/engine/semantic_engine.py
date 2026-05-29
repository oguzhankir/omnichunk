from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import numpy as np
from numpy.typing import NDArray  # noqa: TCH002

from omnichunk.semantic.splitter import SemanticSplitter
from omnichunk.types import Chunk, ChunkingError, ChunkOptions


class SemanticEngine:
    """Engine for embedding-based semantic chunking of prose content."""

    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        splitter = self._build_splitter(options)
        return splitter.split(filepath, content, options)

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        chunks = self.chunk(filepath, content, options)
        for idx, ch in enumerate(chunks):
            yield _with_unknown_total(ch, idx)

    def _build_splitter(self, options: ChunkOptions) -> SemanticSplitter:
        embed_fn = options.semantic_embed_fn
        if embed_fn is None or not callable(embed_fn):
            raise ValueError(
                "semantic=True requires semantic_embed_fn: "
                "Callable[[list[str]], np.ndarray]"
            )
        ss = options.semantic_sentence_splitter
        sentence_fn = ss if callable(ss) else None
        return SemanticSplitter(
            embed_fn=_validated_embed_fn(embed_fn),
            window=int(options.semantic_window),
            threshold=float(options.semantic_threshold),
            min_chunk_sentences=max(1, int(options.semantic_min_sentences)),
            sentence_splitter_fn=sentence_fn,
        )


def _validated_embed_fn(
    embed_fn: Callable[[list[str]], NDArray[Any]],
) -> Callable[[list[str]], NDArray[Any]]:
    """Wrap embed_fn with shape/dtype/value validation.

    Records the expected embedding dimension from the first call and raises
    ChunkingError on any mismatch, non-float dtype, or NaN/Inf values.
    """
    expected_dim: list[int] = []

    def wrapper(texts: list[str]) -> NDArray[Any]:
        result = embed_fn(texts)
        arr = np.asarray(result)

        if arr.ndim != 2 or arr.shape[0] != len(texts):
            raise ChunkingError(
                f"embed_fn must return a 2-D array of shape (N, D) where N is the "
                f"number of input texts; got shape {arr.shape!r} for {len(texts)} texts"
            )

        if not np.issubdtype(arr.dtype, np.floating):
            raise ChunkingError(
                f"embed_fn must return a float array (float32 or float64); "
                f"got dtype {arr.dtype!r}"
            )

        dim = arr.shape[1]
        if expected_dim:
            if dim != expected_dim[0]:
                raise ChunkingError(
                    f"embed_fn returned shape {arr.shape!r} but expected "
                    f"(N, {expected_dim[0]}) — all calls must return the same dimension"
                )
        else:
            expected_dim.append(dim)

        if not np.all(np.isfinite(arr)):
            raise ChunkingError(
                "embed_fn returned embeddings containing NaN or Inf values"
            )

        return arr

    return wrapper


def _with_unknown_total(chunk: Chunk, index: int) -> Chunk:
    return Chunk(
        text=chunk.text,
        contextualized_text=chunk.contextualized_text,
        byte_range=chunk.byte_range,
        line_range=chunk.line_range,
        index=index,
        total_chunks=-1,
        context=chunk.context,
        token_count=chunk.token_count,
        char_count=chunk.char_count,
        nws_count=chunk.nws_count,
    )
