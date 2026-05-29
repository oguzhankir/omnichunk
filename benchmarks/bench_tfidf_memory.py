"""Memory comparison: dense vs sparse TF-IDF for a large document.

Run directly::

    python benchmarks/bench_tfidf_memory.py

Reports the in-memory footprint of the dense ``build_tfidf_matrix`` against
the ``build_tfidf_sparse`` CSR representation for a 2000-sentence document.
Requires scipy for the sparse path (``pip install omnichunk[scipy]``).
"""

from __future__ import annotations

import numpy as np

from omnichunk.semantic.tfidf import build_tfidf_matrix, build_tfidf_sparse


def _synthetic_sentences(n: int = 2000, vocab_size: int = 2048, per: int = 10) -> list[str]:
    rng = np.random.default_rng(7)
    vocab = [f"term{i}" for i in range(vocab_size)]
    return [" ".join(rng.choice(vocab, size=per)) for _ in range(n)]


def main() -> None:
    sentences = _synthetic_sentences()
    dense = build_tfidf_matrix(sentences, max_vocab=2048)
    dense_bytes = int(dense.nbytes)

    sparse = build_tfidf_sparse(sentences, max_vocab=2048)
    if isinstance(sparse, np.ndarray):
        print("scipy not installed; sparse path fell back to dense.")
        print(f"dense bytes: {dense_bytes:,}")
        return

    sparse_bytes = int(
        sparse.data.nbytes + sparse.indices.nbytes + sparse.indptr.nbytes
    )
    reduction = 100.0 * (1.0 - sparse_bytes / dense_bytes)
    print(f"dense  bytes: {dense_bytes:,}")
    print(f"sparse bytes: {sparse_bytes:,}")
    print(f"reduction:    {reduction:.1f}%")


if __name__ == "__main__":
    main()
