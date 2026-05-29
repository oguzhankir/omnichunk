from __future__ import annotations

import numpy as np
import pytest

from omnichunk.engine.semantic_engine import _validated_embed_fn
from omnichunk.types import ChunkingError


def _make_fn(arr: np.ndarray):
    """Return an embed_fn that always yields the given array."""
    def fn(texts: list[str]) -> np.ndarray:
        return arr
    return fn


def _good(n: int, d: int = 4) -> np.ndarray:
    return np.ones((n, d), dtype=np.float32)


# --- 1. wrong shape (1D) -------------------------------------------------------

def test_wrong_shape_raises() -> None:
    fn = _make_fn(np.ones(4, dtype=np.float32))
    wrapped = _validated_embed_fn(fn)
    with pytest.raises(ChunkingError, match="2-D array"):
        wrapped(["a", "b", "c", "d"])


# --- 2. non-float dtype ---------------------------------------------------------

def test_non_float_dtype_raises() -> None:
    fn = _make_fn(np.ones((2, 4), dtype=np.int32))
    wrapped = _validated_embed_fn(fn)
    with pytest.raises(ChunkingError, match="float array"):
        wrapped(["a", "b"])


# --- 3. inconsistent dimension on second call ----------------------------------

def test_dimension_mismatch_raises() -> None:
    call_count = 0

    def fn(texts: list[str]) -> np.ndarray:
        nonlocal call_count
        call_count += 1
        d = 4 if call_count == 1 else 768
        return np.ones((len(texts), d), dtype=np.float64)

    wrapped = _validated_embed_fn(fn)
    wrapped(["first"])  # records dim=4
    with pytest.raises(ChunkingError, match="expected.*4.*all calls must return the same dimension"):
        wrapped(["second"])


# --- 4. NaN values --------------------------------------------------------------

def test_nan_values_raise() -> None:
    arr = np.ones((2, 4), dtype=np.float32)
    arr[0, 1] = float("nan")
    fn = _make_fn(arr)
    wrapped = _validated_embed_fn(fn)
    with pytest.raises(ChunkingError, match="NaN or Inf"):
        wrapped(["a", "b"])


# --- 5. Inf values --------------------------------------------------------------

def test_inf_values_raise() -> None:
    arr = np.ones((3, 4), dtype=np.float64)
    arr[2, 0] = float("inf")
    fn = _make_fn(arr)
    wrapped = _validated_embed_fn(fn)
    with pytest.raises(ChunkingError, match="NaN or Inf"):
        wrapped(["a", "b", "c"])


# --- 6. valid embedding passes without error -----------------------------------

def test_valid_embedding_passes() -> None:
    wrapped = _validated_embed_fn(lambda texts: _good(len(texts)))
    result = wrapped(["hello", "world"])
    assert result.shape == (2, 4)
    assert result.dtype == np.float32


# --- 7. dimension is recorded correctly and re-used ----------------------------

def test_consistent_dimension_passes_second_call() -> None:
    wrapped = _validated_embed_fn(lambda texts: _good(len(texts), d=16))
    wrapped(["first call"])
    wrapped(["second", "call"])  # same d=16, should not raise
