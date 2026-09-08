"""Exercise the optional Rust adapter independently of a compiled wheel."""

from __future__ import annotations

import builtins
from types import SimpleNamespace

import numpy as np
import pytest

from omnichunk.semantic.boundaries import _batch_cosine_similarity
from omnichunk.sizing import rust_accel


@pytest.fixture(autouse=True)
def isolated_backend_cache():
    rust_accel.reset_rust_backend_cache()
    yield
    rust_accel.reset_rust_backend_cache()


def install_adapter(monkeypatch, **functions):
    module = SimpleNamespace(preprocess_nws_cumsum_bytes=lambda raw: [], **functions)
    monkeypatch.setattr(rust_accel.importlib, "import_module", lambda name: module)
    return module


def test_incompatible_extension_is_reported_and_auto_recovers(monkeypatch) -> None:
    monkeypatch.setattr(rust_accel.importlib, "import_module", lambda name: SimpleNamespace())
    status = rust_accel.nws_backend_status("auto")
    assert status["available"] is False
    assert status["active"] is False
    assert "preprocess_nws_cumsum_bytes" in status["reason"]
    assert rust_accel.maybe_preprocess_nws_cumsum_rust("source", backend="auto") is None
    with pytest.raises(RuntimeError, match="explicitly requested"):
        rust_accel.maybe_preprocess_nws_cumsum_rust("source", backend="rust")


def test_python_backend_bypasses_available_extension(monkeypatch) -> None:
    install_adapter(monkeypatch)
    status = rust_accel.nws_backend_status("python")
    assert status == {"selected": "python", "available": True, "active": False, "reason": ""}
    assert rust_accel.maybe_preprocess_nws_cumsum_rust("source", backend="python") is None


@pytest.mark.parametrize("numpy_available", [True, False])
def test_nws_adapter_passes_utf8_bytes_and_supports_missing_numpy(
    monkeypatch, numpy_available
) -> None:
    received = []
    expected = [0, 1, 1, 1, 1]
    module = install_adapter(monkeypatch)

    def preprocess(raw):
        received.append(raw)
        return expected

    module.preprocess_nws_cumsum_bytes = preprocess
    if not numpy_available:
        original = builtins.__import__

        def without_numpy(name, *args, **kwargs):
            if name == "numpy" or name.startswith("numpy."):
                raise ImportError("minimal installation")
            return original(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", without_numpy)
    result = rust_accel.maybe_preprocess_nws_cumsum_rust("a\u2003", backend="rust")
    assert received == [b"a\xe2\x80\x83"]
    assert list(result) == expected
    if numpy_available:
        assert result.dtype == np.int64
    else:
        assert result is expected


def test_cosine_adapter_converts_noncontiguous_input_and_preserves_dimensions(monkeypatch):
    received = []

    def cosine(values, dimensions):
        received.append((values, dimensions))
        return [0.25, 0.5]

    install_adapter(monkeypatch, batch_cosine_similarity_adjacent=cosine)
    embeddings = np.arange(12, dtype=np.float64).reshape(3, 4)[:, ::2]
    result = rust_accel.batch_cosine_similarity_adjacent_rust(embeddings)
    assert received == [([0.0, 2.0, 4.0, 6.0, 8.0, 10.0], 2)]
    np.testing.assert_array_equal(result, [0.25, 0.5])
    assert result.dtype == np.float64


@pytest.mark.parametrize("shape", [(4,), (3, 0)])
def test_cosine_adapter_declines_invalid_dimensions(monkeypatch, shape) -> None:
    def unexpected_call(*args):
        raise AssertionError("Invalid input must not reach the extension")

    install_adapter(monkeypatch, batch_cosine_similarity_adjacent=unexpected_call)
    assert rust_accel.batch_cosine_similarity_adjacent_rust(np.zeros(shape)) is None


@pytest.mark.parametrize("missing_function", [True, False])
def test_cosine_numpy_fallback_when_extension_lacks_kernel_or_kernel_fails(
    monkeypatch, missing_function
) -> None:
    def failing_kernel(*args):
        raise RuntimeError("incompatible extension kernel")

    module = install_adapter(monkeypatch)
    if not missing_function:
        module.batch_cosine_similarity_adjacent = failing_kernel
    vectors = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]])
    np.testing.assert_allclose(_batch_cosine_similarity(vectors), [1.0, 0.0])
