from __future__ import annotations

import numpy as np

from omnichunk.sizing.counter import make_size_counter, make_token_counter
from omnichunk.sizing.nws import get_nws_count, preprocess_nws_cumsum
from omnichunk.sizing.tokenizers import resolve_tokenizer


def test_nws_cumsum_counts_non_whitespace() -> None:
    text = "a b\n\tc"
    cumsum = preprocess_nws_cumsum(text)

    assert isinstance(cumsum, np.ndarray)
    assert get_nws_count(cumsum, 0, len(text.encode("utf-8"))) == 3


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
