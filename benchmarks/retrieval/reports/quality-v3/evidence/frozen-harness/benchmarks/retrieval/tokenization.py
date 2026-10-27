"""Shared benchmark counters with explicit full-model input accounting."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from numbers import Integral
from pathlib import Path

from omnichunk.sizing.counter import make_token_counter


def benchmark_counter(
    unit: str, tokenizer: str, *, include_special_tokens: bool = False
) -> Callable[[str], int]:
    """Use library-default counting, or explicit complete local HF inputs.

    Full-input accounting bypasses provider-dependent encoder normalization in
    the core library. It never downloads a tokenizer or silently substitutes
    tiktoken/approximate counting. Empty strings retain the model's special tokens;
    callers should not render a model input when no passages are retrieved.
    """
    if type(include_special_tokens) is not bool:
        raise ValueError("include_special_tokens must be a boolean")
    if unit not in ("chars", "tokens"):
        raise ValueError("Benchmark size unit must be chars or tokens")
    if not include_special_tokens:
        return len if unit == "chars" else make_token_counter(tokenizer)
    if unit != "tokens":
        raise ValueError("--include-special-tokens requires --unit tokens")
    directory = Path(tokenizer)
    if not directory.is_dir():
        raise ValueError(
            "--include-special-tokens requires an existing local Hugging Face tokenizer directory"
        )
    encoder = import_module("transformers").AutoTokenizer.from_pretrained(
        str(directory.resolve()), local_files_only=True, trust_remote_code=False
    )

    def count(text: str) -> int:
        encoded = encoder.encode(text, add_special_tokens=True, truncation=False)
        if not isinstance(encoded, (list, tuple)) or any(
            isinstance(item, bool) or not isinstance(item, Integral) or item < 0 for item in encoded
        ):
            raise ValueError("Hugging Face encode must return a sequence of nonnegative token IDs")
        return len(encoded)

    return count
