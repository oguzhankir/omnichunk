from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from threading import RLock
from typing import Any

_LOCK = RLock()
_ACTIVE: ContextVar[PluginRegistry | None] = ContextVar("omnichunk_registry", default=None)

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
    if not key or not callable(parser_fn):
        raise ValueError("Parser requires a language and callable")
    with _LOCK:
        if key in _PARSER_REGISTRY and not overwrite:
            raise ValueError(f"Parser for language {key!r} is already registered")
        _PARSER_REGISTRY[key] = parser_fn


def get_parser(lang: str) -> Callable[[str, str], Any] | None:
    """Return registered parser for ``lang``, or ``None``."""
    key = _norm_lang(lang)
    active = _ACTIVE.get()
    if active is not None:
        with active._lock:
            return active.parsers.get(key)
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
    if not callable(formatter_fn):
        raise ValueError("Formatter requires a callable")
    with _LOCK:
        if key in _FORMATTER_REGISTRY and not overwrite:
            raise ValueError(f"Formatter {key!r} is already registered")
        _FORMATTER_REGISTRY[key] = formatter_fn


def get_formatter(name: str) -> Callable[[Sequence[Any]], str] | None:
    """Return registered formatter or ``None``."""
    key = name.strip()
    active = _ACTIVE.get()
    if active is not None:
        with active._lock:
            return active.formatters.get(key)
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


class PluginRegistry:
    """Explicit per-pipeline registry. Mutations are isolated from other chunkers."""

    def __init__(self, *, revision: str = "") -> None:
        self.revision = revision
        self.parsers: dict[str, Callable[[str, str], Any]] = {}
        self.formatters: dict[str, Callable[[Sequence[Any]], str]] = {}
        self._lock = RLock()

    @classmethod
    def from_global(cls) -> PluginRegistry:
        registry = cls()
        with _LOCK:
            registry.parsers.update(_PARSER_REGISTRY)
            registry.formatters.update(_FORMATTER_REGISTRY)
        return registry

    def register_parser(
        self, language: str, parser: Callable[[str, str], Any], *, overwrite: bool = False
    ) -> None:
        key = _norm_lang(language)
        if not key or not callable(parser):
            raise ValueError("Parser requires a language and callable")
        with self._lock:
            if key in self.parsers and not overwrite:
                raise ValueError(f"Parser for {key!r} already registered")
            self.parsers[key] = parser

    def register_formatter(
        self, name: str, formatter: Callable[[Sequence[Any]], str], *, overwrite: bool = False
    ) -> None:
        key = name.strip()
        if not key or not callable(formatter):
            raise ValueError("Formatter requires a name and callable")
        with self._lock:
            if key in self.formatters and not overwrite:
                raise ValueError(f"Formatter {key!r} already registered")
            self.formatters[key] = formatter

    @property
    def fingerprint(self) -> str:
        """Behavior revision plus registered provider identities, without object IDs."""
        from omnichunk.config import _identity

        with self._lock:
            state = {
                "revision": self.revision,
                "parsers": {name: _identity(provider) for name, provider in self.parsers.items()},
                "formatters": {
                    name: _identity(provider) for name, provider in self.formatters.items()
                },
            }
        return hashlib.sha256(
            json.dumps(state, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def iterate(self, iterator: Any) -> Any:
        """Scope each generator advance, restoring context before returning output."""
        iterator = iter(iterator)
        try:
            while True:
                token = _ACTIVE.set(self)
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                finally:
                    _ACTIVE.reset(token)
                yield item
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                token = _ACTIVE.set(self)
                try:
                    close()
                finally:
                    _ACTIVE.reset(token)
