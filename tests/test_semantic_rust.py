"""Tests for Rust cosine similarity backend — skipped if Rust not built."""

from __future__ import annotations

import numpy as np
import pytest

from omnichunk.semantic.boundaries import _batch_cosine_similarity
from omnichunk.sizing.rust_accel import batch_cosine_similarity_adjacent_rust


def test_rust_cosine_matches_numpy_if_available() -> None:
    rng = np.random.default_rng(42)
    emb = rng.standard_normal((10, 16)).astype(np.float32)
    rust_result = batch_cosine_similarity_adjacent_rust(emb)
    if rust_result is None:
        pytest.skip("Rust backend not available")
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    normalized = emb / norms
    expected = np.einsum("id,id->i", normalized[:-1], normalized[1:])
    np.testing.assert_allclose(rust_result, expected, atol=1e-5)


def test_batch_cosine_similarity_output_shape() -> None:
    emb = np.eye(5, 8)
    result = _batch_cosine_similarity(emb)
    assert result.shape == (4,)


def test_batch_cosine_similarity_identical_vectors() -> None:
    v = np.array([[1.0, 0.0, 0.0]] * 4)
    result = _batch_cosine_similarity(v)
    np.testing.assert_allclose(result, 1.0, atol=1e-6)


def test_batch_cosine_similarity_zero_vectors() -> None:
    v = np.zeros((3, 4))
    result = _batch_cosine_similarity(v)
    assert result.shape == (2,)
    assert not np.any(np.isnan(result))


def test_batch_cosine_similarity_orthogonal() -> None:
    v = np.eye(4, 4)
    result = _batch_cosine_similarity(v)
    np.testing.assert_allclose(result, 0.0, atol=1e-6)
