from __future__ import annotations

import numpy as np

from omnichunk import Chunker
from omnichunk.semantic.cache import EmbeddingCache


def _counting_embed(counter: dict[str, int], dim: int = 8):
    rng = np.random.default_rng(0)
    table: dict[str, np.ndarray] = {}

    def embed(texts: list[str]) -> np.ndarray:
        counter["calls"] += 1
        counter["texts"] += len(texts)
        rows = []
        for t in texts:
            if t not in table:
                table[t] = rng.standard_normal(dim)
            rows.append(table[t])
        return np.array(rows)

    return embed


def test_cache_empty_on_new_chunker() -> None:
    chunker = Chunker(max_chunk_size=100, size_unit="chars")
    assert chunker.semantic_cache_stats() == {"hits": 0, "misses": 0, "size": 0}


def test_cache_avoids_reembedding_identical_input() -> None:
    counter = {"calls": 0, "texts": 0}
    embed = _counting_embed(counter)
    chunker = Chunker(max_chunk_size=120, size_unit="chars")
    text = "Sentence one here. Sentence two here.\n\nNew topic now. Another line here."

    chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    first_texts = counter["texts"]
    assert first_texts > 0
    stats_after_first = chunker.semantic_cache_stats()
    assert stats_after_first["misses"] > 0
    assert stats_after_first["size"] > 0

    # Second identical call must hit the cache for every window → zero new embeds.
    texts_before = counter["texts"]
    chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    assert counter["texts"] == texts_before
    assert chunker.semantic_cache_stats()["hits"] > stats_after_first["hits"]


def test_cache_is_per_instance() -> None:
    counter = {"calls": 0, "texts": 0}
    embed = _counting_embed(counter)
    text = "Alpha beta gamma. Delta epsilon zeta.\n\nNew section here. Tail sentence."

    c1 = Chunker(max_chunk_size=120, size_unit="chars")
    c1.semantic_chunk("doc.md", text, embed_fn=embed)
    embeds_after_c1 = counter["texts"]

    # A brand-new Chunker shares nothing → it must re-embed.
    c2 = Chunker(max_chunk_size=120, size_unit="chars")
    assert c2.semantic_cache_stats() == {"hits": 0, "misses": 0, "size": 0}
    c2.semantic_chunk("doc.md", text, embed_fn=embed)
    assert counter["texts"] > embeds_after_c1


def test_lru_eviction_respects_max_size() -> None:
    cache = EmbeddingCache(max_size=2)
    calls = {"n": 0}

    def embed(texts: list[str]) -> np.ndarray:
        calls["n"] += 1
        return np.array([[float(len(t))] for t in texts])

    cached = cache.wrap(embed)
    cached(["a"])  # store a
    cached(["b"])  # store b
    cached(["c"])  # store c -> evict a (LRU)
    assert cache.stats()["size"] == 2

    # "a" was evicted -> miss again; "c" still present -> hit.
    calls_before = calls["n"]
    cached(["c"])
    assert calls["n"] == calls_before  # hit, no embed call
    cached(["a"])
    assert calls["n"] == calls_before + 1  # miss, one embed call


def test_cache_disabled_when_size_zero() -> None:
    counter = {"calls": 0, "texts": 0}
    embed = _counting_embed(counter)
    text = "One sentence. Two sentence.\n\nThree sentence. Four sentence."
    chunker = Chunker(
        max_chunk_size=120, size_unit="chars", semantic_embed_cache_size=0
    )
    chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    embeds_first = counter["texts"]
    chunker.semantic_chunk("doc.md", text, embed_fn=embed)
    # No caching -> identical second call re-embeds everything.
    assert counter["texts"] == 2 * embeds_first
    assert chunker.semantic_cache_stats()["size"] == 0


def test_dedup_within_single_batch() -> None:
    cache = EmbeddingCache(max_size=16)
    calls = {"n": 0, "texts": 0}

    def embed(texts: list[str]) -> np.ndarray:
        calls["n"] += 1
        calls["texts"] += len(texts)
        return np.array([[float(len(t))] for t in texts])

    cached = cache.wrap(embed)
    out = cached(["x", "x", "x"])
    assert out.shape == (3, 1)
    # Three identical inputs -> embed_fn sees the distinct text once.
    assert calls["texts"] == 1
    assert cache.stats()["misses"] == 1
