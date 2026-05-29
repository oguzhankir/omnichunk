"""Per-Chunker LRU cache for sentence/window embeddings.

The semantic engine embeds short text windows during boundary detection.
Documents that share boilerplate (code docs, repeated headers, license
banners) embed the *same* text repeatedly. This module wraps a user
``embed_fn`` with an LRU cache keyed by ``sha256(text)`` so identical text
is embedded at most once for the lifetime of a :class:`~omnichunk.Chunker`.

Determinism: the cache never changes the values returned by ``embed_fn`` —
a cache hit returns the exact array a miss would have computed. It only
removes redundant calls.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """LRU cache of embedding vectors keyed by ``sha256`` of the input text.

    Not thread-safe by design: a :class:`~omnichunk.Chunker` owns one cache
    and concurrent semantic chunking on a single instance is not supported
    (use separate Chunker instances per thread).
    """

    def __init__(self, max_size: int = 4096) -> None:
        self._max = max(0, int(max_size))
        self._store: OrderedDict[str, NDArray[Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict[str, int]:
        """Return ``{"hits", "misses", "size"}`` for the current cache state."""
        return {"hits": self.hits, "misses": self.misses, "size": len(self._store)}

    def clear(self) -> None:
        self._store.clear()
        self.hits = 0
        self.misses = 0

    def wrap(
        self, embed_fn: Callable[[list[str]], NDArray[Any]]
    ) -> Callable[[list[str]], NDArray[Any]]:
        """Return a caching wrapper around ``embed_fn``.

        The wrapper accepts a list of texts and returns a 2D array with one
        row per input (in order). Only cache misses are forwarded to
        ``embed_fn``; duplicate misses within a single batch are de-duplicated
        so ``embed_fn`` sees each distinct missing text exactly once.
        """

        def cached_embed(texts: list[str]) -> NDArray[Any]:
            n = len(texts)
            results: list[NDArray[Any] | None] = [None] * n
            # key -> list of result indices awaiting that vector
            pending: OrderedDict[str, list[int]] = OrderedDict()
            pending_text: dict[str, str] = {}

            for i, text in enumerate(texts):
                k = _key(text)
                cached = self._store.get(k)
                if cached is not None:
                    self.hits += 1
                    self._store.move_to_end(k)
                    results[i] = cached
                elif k in pending:
                    pending[k].append(i)
                else:
                    self.misses += 1
                    pending[k] = [i]
                    pending_text[k] = text

            if pending:
                batch = [pending_text[k] for k in pending]
                computed = np.asarray(embed_fn(batch))
                if computed.ndim != 2 or computed.shape[0] != len(batch):
                    raise ValueError(
                        "embed_fn must return a 2D array with one row per input; "
                        f"got shape {computed.shape} for {len(batch)} texts"
                    )
                for row, k in enumerate(pending):
                    vec = computed[row]
                    if self._max:
                        self._store[k] = vec
                        self._store.move_to_end(k)
                    for idx in pending[k]:
                        results[idx] = vec
                while self._max and len(self._store) > self._max:
                    self._store.popitem(last=False)

            return np.array([r for r in results])

        return cached_embed
