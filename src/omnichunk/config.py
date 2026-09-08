"""Validated public options and reproducible behavior fingerprints."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import fields
from enum import Enum
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Any, get_args

from omnichunk.types import ChunkOptions, ContentType, Language


def public_options(options: ChunkOptions) -> dict[str, Any]:
    """Shallow configuration copy; never clone a model, tracer or callback."""
    return {f.name: getattr(options, f.name) for f in fields(options) if not f.name.startswith("_")}


def coerce_options(options: dict[str, object]) -> dict[str, Any]:
    allowed = {f.name for f in fields(ChunkOptions) if not f.name.startswith("_")}
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise TypeError(f"Unknown or internal chunk option(s): {', '.join(unknown)}")
    return dict(options)


def validate_options(options: ChunkOptions) -> None:
    for name, minimum in [
        ("max_chunk_size", 1),
        ("min_chunk_size", 0),
        ("max_siblings", 0),
        ("overlap_lines", 0),
        ("semantic_window", 1),
        ("semantic_min_sentences", 1),
        ("semantic_embed_cache_size", 0),
    ]:
        value = getattr(options, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    if options.min_chunk_size > options.max_chunk_size:
        raise ValueError("min_chunk_size must not exceed max_chunk_size")
    choices = {
        "size_unit": ("chars", "tokens", "nws"),
        "nws_backend": ("auto", "python", "rust"),
        "context_mode": ("none", "minimal", "full"),
        "sibling_detail": ("none", "names", "signatures"),
        "coverage_policy": ("lossless", "retrieval"),
        "overflow_policy": ("split", "error", "preserve"),
        "context_overflow": ("omit", "error"),
    }
    for name, values in choices.items():
        if getattr(options, name) not in values:
            raise ValueError(f"{name} must be one of {values}")
    for name in (
        "include_imports",
        "filter_imports",
        "preserve_decorators",
        "preserve_comments",
        "include_header_in_sections",
        "include_notebook_outputs",
        "semantic",
    ):
        if not isinstance(getattr(options, name), bool):
            raise ValueError(f"{name} must be a boolean")
    for name in ("filepath", "semantic_model_revision", "semantic_preprocessing"):
        if not isinstance(getattr(options, name), str):
            raise ValueError(f"{name} must be a string")
    for name in ("source_id", "semantic_cache_namespace"):
        value = getattr(options, name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"{name} must be a string or None")
    if options.source_id is not None and not options.source_id.strip():
        raise ValueError("source_id must not be empty")
    tokenizer = options.tokenizer
    if (
        tokenizer is not None
        and not isinstance(tokenizer, str)
        and not callable(tokenizer)
        and not callable(getattr(tokenizer, "encode", None))
    ):
        raise TypeError("tokenizer must be a name, encoder, or counting callable")
    if isinstance(tokenizer, str) and not tokenizer.strip():
        raise ValueError("tokenizer name must not be empty")
    if options.semantic_embed_fn is not None and not callable(options.semantic_embed_fn):
        raise ValueError("semantic_embed_fn must be callable")
    if options.context_mode == "none" and options.overlap_lines:
        raise ValueError(
            "overlap_lines requires rendered context; use overlap with context_mode=none"
        )
    if options.size_unit == "tokens" and options.tokenizer is None:
        raise ValueError(
            "size_unit='tokens' requires an explicit tokenizer; use 'approximate' for estimates"
        )
    if options.language is not None and options.language not in get_args(Language):
        raise ValueError(f"Unsupported language: {options.language}")
    if options.content_type is not None and not isinstance(options.content_type, ContentType):
        raise ValueError("content_type must be a ContentType")
    overlap = options.overlap
    if overlap is not None:
        if (
            isinstance(overlap, bool)
            or not isinstance(overlap, int | float)
            or not math.isfinite(overlap)
        ):
            raise ValueError("overlap must be a nonnegative integer or a fraction below 1")
        if overlap < 0 or (isinstance(overlap, float) and overlap >= 1):
            raise ValueError("overlap must be a nonnegative integer or a fraction below 1")
        if isinstance(overlap, int) and overlap >= options.max_chunk_size:
            raise ValueError("overlap must be smaller than max_chunk_size")
    if options.overlap and options.overlap_lines:
        raise ValueError("Choose overlap or overlap_lines, not both")
    for name in ("preserve_decorators", "preserve_comments", "include_header_in_sections"):
        if getattr(options, name) is not True:
            raise ValueError(f"{name}=False is unsupported; preservation is always enabled")
    if options.semantic and not callable(options.semantic_embed_fn):
        raise ValueError("semantic=True requires a callable semantic_embed_fn")
    if options.semantic_sentence_splitter is not None and not callable(
        options.semantic_sentence_splitter
    ):
        raise ValueError("semantic_sentence_splitter must be callable")
    if (
        isinstance(options.semantic_threshold, bool)
        or not isinstance(options.semantic_threshold, int | float)
        or not math.isfinite(options.semantic_threshold)
    ):
        raise ValueError("semantic_threshold must be finite")
    if not 0 <= options.semantic_threshold <= 1:
        raise ValueError("semantic_threshold must be between 0 and 1")
    if options.algorithm_version != "2.1":
        raise ValueError("Only algorithm_version='2.1' is supported")


def _primitive_state(value: Any, depth: int = 0) -> tuple[bool, Any]:
    """Select deterministic configuration state without serializing model objects."""
    if isinstance(value, Enum):
        return _primitive_state(value.value, depth)
    if value is None or isinstance(value, str | int | bool):
        return True, value
    if isinstance(value, float):
        return True, value if math.isfinite(value) else str(value)
    if depth >= 8:
        return False, None
    if isinstance(value, list | tuple):
        items = [_primitive_state(item, depth + 1) for item in value]
        return all(ok for ok, _ in items), [item for _, item in items]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        entries = {key: _primitive_state(item, depth + 1) for key, item in value.items()}
        return all(ok for ok, _ in entries.values()), {
            key: item for key, (_, item) in entries.items()
        }
    return False, None


def _identity(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    explicit = getattr(value, "fingerprint", None)
    if isinstance(explicit, str):
        return {"fingerprint": explicit}
    if hasattr(value, "__wrapped__"):
        return _identity(value.__wrapped__)
    identity: dict[str, Any] = {
        "callable": f"{getattr(value, '__module__', type(value).__module__)}."
        f"{getattr(value, '__qualname__', type(value).__qualname__)}"
    }
    # Standard tokenizers and local embedders expose their model configuration.
    # User providers can supply a fingerprint to exclude transient public state.
    state: dict[str, Any] = {}
    for name, item in getattr(value, "__dict__", {}).items():
        if not name.startswith("_"):
            valid, primitive = _primitive_state(item)
            if valid:
                state[name] = primitive
    for name in ("model_name", "name_or_path", "name", "revision"):
        item = getattr(value, name, None)
        if isinstance(item, str):
            state[name] = item
    if state:
        identity["configuration"] = state
    return identity


@lru_cache(maxsize=1)
def _dependency_versions() -> dict[str, str | None]:
    dependencies: dict[str, str | None] = {}
    for package in (
        "tree-sitter",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
        "tree-sitter-rust",
        "tree-sitter-go",
        "tree-sitter-java",
        "tree-sitter-c",
        "tree-sitter-cpp",
        "tree-sitter-c-sharp",
        "tree-sitter-ruby",
        "tree-sitter-php",
        "tree-sitter-kotlin",
        "tree-sitter-swift",
        "tree-sitter-sql",
        "tree-sitter-bash",
        "tree-sitter-scala",
        "tree-sitter-elixir",
        "tiktoken",
        "transformers",
    ):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = None
    return dependencies


def configuration_fingerprint(options: ChunkOptions) -> str:
    ignored = {"filepath", "source_id", "otel_tracer", "semantic_embed_cache_size"}
    payload = {k: _identity(v) for k, v in public_options(options).items() if k not in ignored}
    payload["dependencies"] = _dependency_versions()
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
