"""Semantic API wiring with an offline lexical embedding; no model download.

The tiny fixed vocabulary below is a teaching aid, not a production embedding
model or evidence of retrieval quality. Replace ``embed`` with a fixed-version
model whose output depends only on its input text, not the batch position.
"""

from __future__ import annotations

import re

import numpy as np

from omnichunk import Chunker
from omnichunk.semantic import (
    SemanticSplitter,
    detect_semantic_boundaries,
    detect_topic_shifts,
    split_sentences,
)
from omnichunk.types import ChunkOptions, ContentType


def embed(texts: list[str]) -> np.ndarray:
    vocabulary = ("cats", "cars", "roads", "hello", "world")
    vectors = np.zeros((len(texts), len(vocabulary) + 1), dtype=np.float32)
    for row, text in enumerate(texts):
        words = re.findall(r"\w+", text.casefold())
        for column, word in enumerate(vocabulary):
            vectors[row, column] = words.count(word)
        # A background feature keeps out-of-vocabulary inputs nonzero.
        vectors[row, -1] = 0.1
    return vectors


def main() -> None:
    assert np.array_equal(embed(["cats", "cars"])[0], embed(["cats"])[0])
    essay = "First sentence about cats. Second sentence about cats. " * 4
    essay += "Now we switch to cars entirely. Cars drive on roads. " * 4

    triples = split_sentences(essay)
    sents = [t for t, _, _ in triples]
    print(f"sentences: {len(sents)}")

    bres = detect_semantic_boundaries(sents, embed_fn=embed, window=1, threshold=0.2)
    assert 7 in bres.boundary_indices
    print(f"boundary_indices: {bres.boundary_indices[:10]}")
    print(f"similarity_scores (first 5): {tuple(round(x, 4) for x in bres.similarity_scores[:5])}")

    chunker = Chunker(max_chunk_size=256, size_unit="chars")
    sem_chunks = chunker.semantic_chunk("essay.md", essay, embed_fn=embed, window=1, threshold=0.2)
    print(f"semantic_chunk count: {len(sem_chunks)}")
    if sem_chunks:
        print(f"  first chunk: {sem_chunks[0].text[:80]!r}…")

    # Many short sentences for topic-shift (needs n >= 2*window)
    long_sents = ["Cats chase mice and climb trees."] * 15 + [
        "Cars drive along roads using engines."
    ] * 15
    shifts = detect_topic_shifts(long_sents, window=5, threshold=0.35)
    print(f"topic shift indices (sample): {shifts[:5]}")

    text = "Hello world. " * 3
    opts = ChunkOptions(
        max_chunk_size=200,
        size_unit="chars",
        filepath="p.md",
        language="plaintext",
        content_type=ContentType.PROSE,
    )
    splitter = SemanticSplitter(embed_fn=embed, window=2, threshold=0.25)
    direct = splitter.split("p.md", text, opts)
    print(f"SemanticSplitter.split count: {len(direct)}")


if __name__ == "__main__":
    main()
