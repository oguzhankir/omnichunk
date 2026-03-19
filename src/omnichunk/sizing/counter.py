from __future__ import annotations

from functools import lru_cache
from typing import Callable, Literal

from .tokenizers import resolve_tokenizer


def make_token_counter(
    tokenizer: str | Callable[[str], int] | object | None,
    *,
    max_token_chars: int | None = None,
    chunk_size: int | None = None,
    cache_maxsize: int | None = 16384,
) -> Callable[[str], int]:
    """Create a memoized token counter with optional long-text short-circuit."""
    token_counter = resolve_tokenizer(tokenizer)

    @lru_cache(maxsize=cache_maxsize)
    def _memoized_count(text: str) -> int:
        if not text:
            return 0

        if (
            max_token_chars is not None
            and chunk_size is not None
            and chunk_size > 0
            and len(text) > chunk_size * 6
        ):
            probe_len = min(len(text), chunk_size * 6 + max_token_chars)
            probe_count = token_counter(text[:probe_len])
            if probe_count > chunk_size:
                return chunk_size + 1

        return token_counter(text)

    return _memoized_count


def make_size_counter(
    size_unit: Literal["tokens", "chars", "nws"],
    tokenizer: str | Callable[[str], int] | object | None = None,
    *,
    max_token_chars: int | None = None,
    chunk_size: int | None = None,
    cache_maxsize: int | None = 16384,
) -> Callable[[str], int]:
    """Create a generic chunk size counter."""
    if size_unit == "chars":
        return len
    if size_unit == "nws":
        return lambda text: sum(1 for ch in text if not ch.isspace())
    return make_token_counter(
        tokenizer,
        max_token_chars=max_token_chars,
        chunk_size=chunk_size,
        cache_maxsize=cache_maxsize,
    )
