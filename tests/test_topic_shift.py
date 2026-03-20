from __future__ import annotations

import numpy as np

from omnichunk.semantic.tfidf import build_tfidf_matrix, detect_topic_shifts


def test_build_tfidf_matrix_shape() -> None:
    docs = ["the quick brown fox", "machine learning is great", "fox is quick"]
    mat = build_tfidf_matrix(docs)
    assert mat.shape[0] == 3
    assert mat.shape[1] > 0


def test_build_tfidf_matrix_l2_normalized() -> None:
    docs = ["hello world", "foo bar baz"]
    mat = build_tfidf_matrix(docs)
    norms = np.linalg.norm(mat, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-6)


def test_build_tfidf_matrix_empty_docs() -> None:
    mat = build_tfidf_matrix(["", ""])
    assert mat.shape[0] == 2


def test_detect_topic_shifts_returns_tuple() -> None:
    sentences = ["The cat sat."] * 5 + ["Deep learning changed AI."] * 5
    shifts = detect_topic_shifts(sentences, window=2, threshold=0.3)
    assert isinstance(shifts, tuple)
    assert all(isinstance(i, int) for i in shifts)


def test_detect_topic_shifts_deterministic() -> None:
    sentences = ["alpha beta gamma."] * 4 + ["delta epsilon zeta."] * 4
    r1 = detect_topic_shifts(sentences, window=2, threshold=0.4)
    r2 = detect_topic_shifts(sentences, window=2, threshold=0.4)
    assert r1 == r2


def test_detect_topic_shifts_too_short_returns_empty() -> None:
    shifts = detect_topic_shifts(["one."], window=3)
    assert shifts == ()
