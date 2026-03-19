from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _fallback_counter(text: str) -> int:
    if not text:
        return 0
    return len(text.split())


def _normalize_encoder_counter(encoder: Any) -> Callable[[str], int]:
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
        if isinstance(encoded, list):
            return len(encoded)
        return len(list(encoded))

    return counter


def resolve_tokenizer(
    tokenizer_or_name: str | Callable[[str], int] | Any | None,
) -> Callable[[str], int]:
    """Resolve tokenizer-like input into a token counting callable.

    Supported inputs:
    - str: tiktoken model/encoding name, then transformers tokenizer id (local only)
    - callable: treated as counter directly
    - tokenizer-like object with .encode(...)
    - None: fallback whitespace-token counter
    """
    if tokenizer_or_name is None:
        return _fallback_counter

    if callable(tokenizer_or_name):
        return tokenizer_or_name

    if isinstance(tokenizer_or_name, str):
        name = tokenizer_or_name.strip()

        try:
            import tiktoken  # type: ignore

            try:
                enc = tiktoken.encoding_for_model(name)
                return _normalize_encoder_counter(enc)
            except Exception:
                enc = tiktoken.get_encoding(name)
                return _normalize_encoder_counter(enc)
        except Exception:
            pass

        try:
            from transformers import AutoTokenizer  # type: ignore

            hf_tokenizer = AutoTokenizer.from_pretrained(name, local_files_only=True)
            return _normalize_encoder_counter(hf_tokenizer)
        except Exception:
            return _fallback_counter

    encode = getattr(tokenizer_or_name, "encode", None)
    if callable(encode):
        return _normalize_encoder_counter(tokenizer_or_name)

    return _fallback_counter
