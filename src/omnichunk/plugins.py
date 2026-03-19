from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import RLock
from typing import Any

_LOCK = RLock()

_PARSER_REGISTRY: dict[str, Callable[[str, str], Any]] = {}
_FORMATTER_REGISTRY: dict[str, Callable[[Sequence[Any]], str]] = {}


def _norm_lang(lang: str) -> str:
    return lang.strip().lower()


def register_parser(
    lang: str,
    parser_fn: Callable[[str, str], Any],
    *,
    overwrite: bool = False,
) -> None:
    """Register ``parser_fn(filepath, content)`` returning a tree-like object or ``None``."""
    key = _norm_lang(lang)
    with _LOCK:
        if key in _PARSER_REGISTRY and not overwrite:
            raise ValueError(f"Parser for language {key!r} is already registered")
        _PARSER_REGISTRY[key] = parser_fn


def get_parser(lang: str) -> Callable[[str, str], Any] | None:
    """Return registered parser for ``lang``, or ``None``."""
    key = _norm_lang(lang)
    with _LOCK:
        return _PARSER_REGISTRY.get(key)


def register_formatter(
    name: str,
    formatter_fn: Callable[[Sequence[Any]], str],
    *,
    overwrite: bool = False,
) -> None:
    """Register a custom output formatter: ``(chunks) -> str``."""
    key = name.strip()
    if not key:
        raise ValueError("Formatter name must be non-empty")
    with _LOCK:
        if key in _FORMATTER_REGISTRY and not overwrite:
            raise ValueError(f"Formatter {key!r} is already registered")
        _FORMATTER_REGISTRY[key] = formatter_fn


def get_formatter(name: str) -> Callable[[Sequence[Any]], str] | None:
    """Return registered formatter or ``None``."""
    key = name.strip()
    with _LOCK:
        return _FORMATTER_REGISTRY.get(key)


def list_registered_parsers() -> list[str]:
    with _LOCK:
        return sorted(_PARSER_REGISTRY)


def list_registered_formatters() -> list[str]:
    with _LOCK:
        return sorted(_FORMATTER_REGISTRY)


def clear_registry() -> None:
    """Clear parsers and formatters. For tests only."""
    with _LOCK:
        _PARSER_REGISTRY.clear()
        _FORMATTER_REGISTRY.clear()
