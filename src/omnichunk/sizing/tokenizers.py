from __future__ import annotations

from collections.abc import Callable
from numbers import Integral
from typing import Any


def _fallback_counter(text: str) -> int:
    """Whitespace estimate, never an exact model-token count."""
    return len(text.split())


def _validated_counter(counter_fn: Callable[[str], Any]) -> Callable[[str], int]:
    def counter(text: str) -> int:
        value = counter_fn(text)
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
            raise ValueError("tokenizer counter must return a non-negative integer")
        return int(value)

    return counter


def _normalize_encoder_counter(encoder: Any) -> Callable[[str], int]:
    truncation = getattr(encoder, "truncation", None)
    if truncation is not None and truncation is not False:
        raise ValueError("Disable tokenizer truncation before using it for exact token counting")

    def counter(text: str) -> int:
        if not text:
            return 0
        try:
            encoded = encoder.encode(text, disallowed_special=())
        except TypeError:
            try:
                encoded = encoder.encode(text, add_special_tokens=False)
            except TypeError:
                encoded = encoder.encode(text)
        if hasattr(encoded, "ids"):
            return len(encoded.ids)
        return len(list(encoded))

    return counter


def resolve_tokenizer(
    tokenizer_or_name: str | Callable[[str], int] | Any | None,
) -> Callable[[str], int]:
    """Resolve a counter or encoder; named providers fail instead of estimating.

    Names use tiktoken first, then a locally installed Hugging Face tokenizer.
    ``approximate`` explicitly selects whitespace estimation. ``None`` retains
    the same estimate for internal informational metadata; token-budget APIs
    must require an explicitly selected tokenizer.
    """
    if tokenizer_or_name is None:
        return _fallback_counter
    if isinstance(tokenizer_or_name, str):
        name = tokenizer_or_name.strip()
        if not name:
            raise ValueError("tokenizer name must not be empty")
        if name == "approximate":
            return _fallback_counter
        try:
            import tiktoken

            try:
                encoder = tiktoken.encoding_for_model(name)
            except KeyError:
                encoder = tiktoken.get_encoding(name)
            return _normalize_encoder_counter(encoder)
        except (ImportError, ValueError, KeyError, OSError):
            pass
        try:
            from transformers import AutoTokenizer  # type: ignore[import-not-found]

            encoder = AutoTokenizer.from_pretrained(name, local_files_only=True)
        except (ImportError, ValueError, OSError) as exc:
            raise ValueError(
                f"Cannot resolve tokenizer {name!r}. Install omnichunk[tiktoken] or "
                "omnichunk[transformers] and make the tokenizer available locally, "
                "pass an encoder/counter, or explicitly select 'approximate'."
            ) from exc
        return _normalize_encoder_counter(encoder)
    if callable(getattr(tokenizer_or_name, "encode", None)):
        return _normalize_encoder_counter(tokenizer_or_name)
    if callable(tokenizer_or_name):
        return _validated_counter(tokenizer_or_name)
    raise TypeError("tokenizer must be a name, encoder object, or token-counting callable")
