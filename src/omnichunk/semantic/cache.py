"""Thread-safe, provider-scoped LRU caching for deterministic embeddings."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from collections.abc import Callable
from functools import wraps
from threading import RLock
from typing import Any

import numpy as np
from numpy.typing import NDArray


class EmbeddingCache:
    """Cache vectors by provider identity, revision, preprocessing and source text.

    A lock serializes cache misses, including provider calls, so concurrent uses
    cannot mix model outputs or compute the same missing batch more than once.
    Cache only deterministic providers. When mutating a provider's model or
    preprocessing, change the corresponding namespace field or clear the cache.
    """

    def __init__(self, max_size: int = 4096) -> None:
        self._max = max(0, int(max_size))
        self._store: OrderedDict[tuple[Any, ...], NDArray[Any]] = OrderedDict()
        self._providers: dict[int, object] = {}
        self._dimensions: dict[tuple[Any, ...], int] = {}
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"hits": self.hits, "misses": self.misses, "size": len(self._store)}

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._dimensions.clear()
            self._providers.clear()
            self.hits = self.misses = 0

    def wrap(
        self,
        embed_fn: Callable[[list[str]], NDArray[Any]],
        *,
        namespace: str | None = None,
        model_revision: str = "",
        preprocessing: str = "",
    ) -> Callable[[list[str]], NDArray[Any]]:
        """Wrap a provider without sharing vectors with another callable.

        Bound methods use the instance/function pair as identity. The optional
        namespace, model revision and preprocessing revision further partition
        that provider's cache. Provider references prevent Python object ID reuse.
        """
        owner = getattr(embed_fn, "__self__", None)
        function = getattr(embed_fn, "__func__", None)
        identity = (id(owner), id(function)) if function is not None else (id(embed_fn),)
        scope = (identity, namespace, model_revision, preprocessing)

        @wraps(embed_fn)
        def cached_embed(texts: list[str]) -> NDArray[Any]:
            with self._lock:
                # Retain identities even when a wrapper survives clear().
                if function is not None:
                    self._providers[id(owner)] = owner
                    self._providers[id(function)] = function
                else:
                    self._providers[id(embed_fn)] = embed_fn
                if not texts:
                    return np.empty((0, self._dimensions.get(scope, 0)), dtype=np.float64)
                results: list[NDArray[Any] | None] = [None] * len(texts)
                pending: OrderedDict[tuple[Any, ...], list[int]] = OrderedDict()
                pending_text: dict[tuple[Any, ...], str] = {}
                for index, text in enumerate(texts):
                    key = (*scope, hashlib.sha256(text.encode("utf-8")).hexdigest())
                    cached = self._store.get(key)
                    if cached is not None:
                        self.hits += 1
                        self._store.move_to_end(key)
                        results[index] = cached
                    elif key in pending:
                        pending[key].append(index)
                    else:
                        self.misses += 1
                        pending[key] = [index]
                        pending_text[key] = text
                if pending:
                    batch = [pending_text[key] for key in pending]
                    computed = np.asarray(embed_fn(batch))
                    if computed.ndim != 2 or computed.shape[0] != len(batch):
                        raise ValueError("embed_fn must return a 2D array with one row per input")
                    if computed.shape[1] < 1 or not np.issubdtype(computed.dtype, np.floating):
                        raise ValueError(
                            "embed_fn must return a float array with a positive dimension"
                        )
                    if not np.all(np.isfinite(computed)):
                        raise ValueError("embed_fn returned NaN or Inf values")
                    expected = self._dimensions.get(scope)
                    if expected is not None and expected != computed.shape[1]:
                        raise ValueError(
                            "embed_fn changed embedding dimension within its namespace"
                        )
                    self._dimensions[scope] = computed.shape[1]
                    for row, key in enumerate(pending):
                        # Providers may reuse their output buffers on the next call.
                        vector = computed[row].copy()
                        if self._max:
                            self._store[key] = vector
                            self._store.move_to_end(key)
                        for index in pending[key]:
                            results[index] = vector
                    while len(self._store) > self._max:
                        self._store.popitem(last=False)
                # Do not expose cache-owned mutable vectors to the caller.
                return np.array(results)

        return cached_embed
