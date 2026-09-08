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


def test_invalid_tokenizer_never_silently_estimates() -> None:
    with pytest.raises(TypeError):
        resolve_tokenizer(object())
    with pytest.raises(ValueError):
        resolve_tokenizer("")
    with pytest.raises(ValueError, match="tokenizer"):
        resolve_tokenizer("omnichunk-this-model-does-not-exist-794621")


def test_encoder_object_takes_precedence_over_callable_interface() -> None:
    class Tokenizer:
        def __call__(self, text):
            return {"input_ids": [1, 2]}

        def encode(self, text, **kwargs):
            return [1, 2]

    assert resolve_tokenizer(Tokenizer())("hello") == 2


@pytest.mark.parametrize("value", [-1, 1.2, True])
def test_invalid_counter_result_rejected(value) -> None:
    with pytest.raises(ValueError):
        resolve_tokenizer(lambda text: value)("hello")


def test_explicit_approximate_tokenizer() -> None:
    assert resolve_tokenizer("approximate")("hello world") == 2


def test_encoder_signature_fallbacks_and_encoding_objects() -> None:
    from types import SimpleNamespace

    class PlainEncoder:
        def encode(self, text):
            return (1, 2, 3)

    class HuggingFaceEncoder:
        def encode(self, text, *, add_special_tokens):
            assert add_special_tokens is False
            return SimpleNamespace(ids=[3, 4])

    assert resolve_tokenizer(PlainEncoder())("source") == 3
    assert resolve_tokenizer(HuggingFaceEncoder())("source") == 2
    assert resolve_tokenizer(HuggingFaceEncoder())("") == 0


def test_named_tiktoken_and_local_huggingface_resolution(monkeypatch) -> None:
    import sys
    from types import SimpleNamespace

    encoder = SimpleNamespace(encode=lambda text, **kwargs: [1, 2])

    def missing(name):
        raise KeyError(name)

    monkeypatch.setitem(
        sys.modules,
        "tiktoken",
        SimpleNamespace(encoding_for_model=lambda name: encoder, get_encoding=missing),
    )
    assert resolve_tokenizer("model-name")("source") == 2
    monkeypatch.setitem(
        sys.modules,
        "tiktoken",
        SimpleNamespace(encoding_for_model=missing, get_encoding=lambda name: encoder),
    )
    assert resolve_tokenizer("encoding-name")("source") == 2
    monkeypatch.setitem(
        sys.modules, "tiktoken", SimpleNamespace(encoding_for_model=missing, get_encoding=missing)
    )

    def local_only(name, *, local_files_only):
        assert local_files_only is True
        return encoder

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoTokenizer=SimpleNamespace(from_pretrained=local_only)),
    )
    assert resolve_tokenizer("local-model")("source") == 2


def test_configured_truncation_is_rejected_for_exact_counting() -> None:
    class TruncatingEncoder:
        truncation = {"max_length": 1}

        def encode(self, text, **kwargs):
            return [1]

    with pytest.raises(ValueError, match="truncation"):
        resolve_tokenizer(TruncatingEncoder())
