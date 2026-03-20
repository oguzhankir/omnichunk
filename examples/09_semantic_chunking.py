"""
Semantic boundaries, Chunker.semantic_chunk, and TF-IDF topic shifts (numpy only).
"""

from __future__ import annotations

import numpy as np

from omnichunk import Chunker
from omnichunk.semantic import (
    SemanticSplitter,
    detect_semantic_boundaries,
    detect_topic_shifts,
    split_sentences,
)
from omnichunk.sizing.nws import preprocess_nws_cumsum
from omnichunk.types import ChunkOptions, ContentType
from omnichunk.util.text_index import TextIndex


def embed(texts: list[str]) -> np.ndarray:
    rng = np.random.default_rng(seed=42)
    return rng.standard_normal((len(texts), 64)).astype(np.float32)


def main() -> None:
    essay = "First sentence about cats. Second sentence about cats. " * 4
    essay += "Now we switch to cars entirely. Cars drive on roads. " * 4

    triples = split_sentences(essay)
    sents = [t for t, _, _ in triples]
    print(f"sentences: {len(sents)}")

    bres = detect_semantic_boundaries(sents, embed_fn=embed, window=2, threshold=0.2)
    print(f"boundary_indices: {bres.boundary_indices[:10]}")
    print(f"similarity_scores (first 5): {tuple(round(x, 4) for x in bres.similarity_scores[:5])}")

    chunker = Chunker(max_chunk_size=256, size_unit="chars")
    sem_chunks = chunker.semantic_chunk("essay.md", essay, embed_fn=embed, window=2, threshold=0.2)
    print(f"semantic_chunk count: {len(sem_chunks)}")
    if sem_chunks:
        print(f"  first chunk: {sem_chunks[0].text[:80]!r}…")

    # Many short sentences for topic-shift (needs n >= 2*window)
    long_sents = [f"Topic A line {i}." for i in range(15)] + [f"Topic B line {i}." for i in range(15)]
    shifts = detect_topic_shifts(long_sents, window=5, threshold=0.35)
    print(f"topic shift indices (sample): {shifts[:5]}")

    text = "Hello world. " * 3
    opts = ChunkOptions(
        max_chunk_size=200,
        size_unit="chars",
        filepath="p.md",
        language="plaintext",
        content_type=ContentType.PROSE,
        _precomputed_text_index=TextIndex(text),
        _precomputed_nws_cumsum=preprocess_nws_cumsum(text, backend="python"),
    )
    splitter = SemanticSplitter(embed_fn=embed, window=2, threshold=0.25)
    direct = splitter.split("p.md", text, opts)
    print(f"SemanticSplitter.split count: {len(direct)}")


if __name__ == "__main__":
    main()
