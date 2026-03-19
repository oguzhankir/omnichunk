from __future__ import annotations

import numpy as np
import pytest

from omnichunk.sizing.counter import make_size_counter, make_token_counter
from omnichunk.sizing.nws import (
    get_nws_backend_status,
    get_nws_count,
    preprocess_nws_cumsum,
    preprocess_nws_cumsum_python,
)
from omnichunk.sizing.rust_accel import reset_rust_backend_cache
from omnichunk.sizing.tokenizers import resolve_tokenizer


def test_nws_cumsum_counts_non_whitespace() -> None:
    text = "a b\n\tc"
    cumsum = preprocess_nws_cumsum(text)

    assert isinstance(cumsum, np.ndarray)
    assert get_nws_count(cumsum, 0, len(text.encode("utf-8"))) == 3


def test_nws_backend_status_shape() -> None:
    status = get_nws_backend_status()
    assert status["selected"] == "auto"
    assert isinstance(status["available"], bool)
    assert isinstance(status["active"], bool)
    assert isinstance(status["reason"], str)


def test_python_backend_matches_default_output() -> None:
    text = "alpha\n\nbeta\t gamma"
    default_cumsum = preprocess_nws_cumsum(text)
    python_cumsum = preprocess_nws_cumsum(text, backend="python")

    assert np.array_equal(default_cumsum, python_cumsum)
    assert np.array_equal(python_cumsum, preprocess_nws_cumsum_python(text))


def test_invalid_nws_backend_raises_value_error() -> None:
    with pytest.raises(ValueError):
        preprocess_nws_cumsum("x", backend="invalid")


def test_forced_rust_backend_behavior() -> None:
    reset_rust_backend_cache()
    status = get_nws_backend_status("rust")
    if bool(status["available"]):
        cumsum = preprocess_nws_cumsum("a b\nc", backend="rust")
        assert get_nws_count(cumsum, 0, len(b"a b\nc")) == 3
    else:
        with pytest.raises(RuntimeError):
            preprocess_nws_cumsum("a b\nc", backend="rust")


def test_get_nws_count_accepts_sequence_inputs() -> None:
    cumsum = [0, 1, 1, 2, 2, 3]
    assert get_nws_count(cumsum, 0, len(cumsum) - 1) == 3
    assert get_nws_count(cumsum, -10, 2) == 1


def test_token_counter_memoized() -> None:
    calls = {"n": 0}

    def counter(text: str) -> int:
        calls["n"] += 1
        return len(text.split())

    memo = make_token_counter(counter)
    assert memo("a b c") == 3
    assert memo("a b c") == 3
    assert calls["n"] == 1


def test_token_counter_short_circuit() -> None:
    def counter(text: str) -> int:
        return len(text)

    memo = make_token_counter(counter, max_token_chars=1, chunk_size=5)
    assert memo("x" * 100) == 6


def test_resolve_tokenizer_callable_and_none() -> None:
    fn = resolve_tokenizer(None)
    assert fn("a b c") == 3

    custom = resolve_tokenizer(lambda text: len(text))
    assert custom("abcd") == 4


def test_make_size_counter_variants() -> None:
    token_size = make_size_counter("tokens", tokenizer=lambda t: len(t.split()))
    char_size = make_size_counter("chars")
    nws_size = make_size_counter("nws")

    text = "a b\n c"
    assert token_size(text) == 3
    assert char_size(text) == len(text)
    assert nws_size(text) == 3
