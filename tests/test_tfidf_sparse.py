from __future__ import annotations

import builtins
import importlib.util

import numpy as np
import pytest

from omnichunk.semantic.tfidf import build_tfidf_matrix, build_tfidf_sparse

_HAVE_SCIPY = importlib.util.find_spec("scipy") is not None

_DOCS = [
    "the quick brown fox jumps over the lazy dog",
    "machine learning models require large training datasets",
    "the fox is quick and the dog is lazy",
    "neural networks learn hierarchical feature representations",
]


def test_dense_builder_unchanged_shape_and_norm() -> None:
    mat = build_tfidf_matrix(_DOCS)
    assert mat.shape[0] == len(_DOCS)
    assert mat.shape[1] > 0
    norms = np.linalg.norm(mat, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-6)


@pytest.mark.skipif(not _HAVE_SCIPY, reason="scipy not installed")
def test_sparse_matches_dense_values() -> None:
    import scipy.sparse as sp

    dense = build_tfidf_matrix(_DOCS)
    sparse = build_tfidf_sparse(_DOCS)
    assert sp.issparse(sparse)
    np.testing.assert_allclose(sparse.toarray(), dense, atol=1e-9)


def test_sparse_falls_back_to_dense_without_scipy(monkeypatch) -> None:
    original = builtins.__import__

    def without_scipy(name, *args, **kwargs):
        if name == "scipy" or name.startswith("scipy."):
            raise ImportError("simulated base installation without SciPy")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_scipy)
    out = build_tfidf_sparse(_DOCS)
    assert isinstance(out, np.ndarray)
    np.testing.assert_allclose(out, build_tfidf_matrix(_DOCS), atol=1e-9)


@pytest.mark.skipif(not _HAVE_SCIPY, reason="scipy not installed")
def test_sparse_memory_at_least_half_smaller_2000_sentences() -> None:
    rng = np.random.default_rng(7)
    vocab = [f"term{i}" for i in range(2048)]
    sentences = [" ".join(rng.choice(vocab, size=10)) for _ in range(2000)]
    dense = build_tfidf_matrix(sentences, max_vocab=2048)
    sparse = build_tfidf_sparse(sentences, max_vocab=2048)

    dense_bytes = int(dense.nbytes)
    sparse_bytes = int(sparse.data.nbytes + sparse.indices.nbytes + sparse.indptr.nbytes)
    assert sparse_bytes <= 0.5 * dense_bytes, f"sparse={sparse_bytes} dense={dense_bytes}"


def test_empty_documents_both_paths() -> None:
    assert build_tfidf_matrix([]).shape[0] == 0
    out = build_tfidf_sparse([])
    # Either a (0, 1) sparse or dense, depending on scipy availability.
    assert out.shape[0] == 0


@pytest.mark.parametrize("documents", [["", "123 !!!"], ["unique", "separate"]])
def test_pruned_vocabulary_produces_finite_zero_rows(documents) -> None:
    dense = build_tfidf_matrix(documents, min_df=3)
    sparse = build_tfidf_sparse(documents, min_df=3)
    assert dense.shape == (len(documents), 1)
    sparse_values = sparse.toarray() if hasattr(sparse, "toarray") else sparse
    np.testing.assert_array_equal(sparse_values, dense)
    assert np.isfinite(dense).all()
    assert not np.any(dense)


def test_vocabulary_limit_discards_rare_terms_consistently() -> None:
    documents = ["common common rare", "common different", ""]
    dense = build_tfidf_matrix(documents, max_vocab=1)
    sparse = build_tfidf_sparse(documents, max_vocab=1)
    sparse_values = sparse.toarray() if hasattr(sparse, "toarray") else sparse
    np.testing.assert_array_equal(dense, [[1.0], [1.0], [0.0]])
    np.testing.assert_allclose(sparse_values, dense)
