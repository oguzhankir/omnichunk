from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from threading import RLock
from typing import Any

from omnichunk.types import Language

try:
    from tree_sitter import Language as _TSLanguage
    from tree_sitter import Parser as _TSParser
except Exception:  # pragma: no cover
    _TSLanguage = None  # type: ignore[misc,assignment]
    _TSParser = None  # type: ignore[misc,assignment]


@dataclass(frozen=True)
class GrammarSpec:
    module_name: str
    callables: tuple[str, ...] = ("language",)


_GRAMMARS: dict[Language, GrammarSpec] = {
    "python": GrammarSpec("tree_sitter_python", ("language",)),
    "javascript": GrammarSpec("tree_sitter_javascript", ("language",)),
    "typescript": GrammarSpec(
        "tree_sitter_typescript", ("language_typescript", "language", "typescript")
    ),
    "rust": GrammarSpec("tree_sitter_rust", ("language",)),
    "go": GrammarSpec("tree_sitter_go", ("language",)),
    "java": GrammarSpec("tree_sitter_java", ("language",)),
    "c": GrammarSpec("tree_sitter_c", ("language",)),
    "cpp": GrammarSpec("tree_sitter_cpp", ("language",)),
    "csharp": GrammarSpec("tree_sitter_c_sharp", ("language", "language_c_sharp")),
    "ruby": GrammarSpec("tree_sitter_ruby", ("language",)),
    "php": GrammarSpec("tree_sitter_php", ("language", "language_php", "language_php_only")),
    "swift": GrammarSpec("tree_sitter_swift", ("language",)),
    "kotlin": GrammarSpec("tree_sitter_kotlin", ("language",)),
}

_LOCK = RLock()


@lru_cache(maxsize=64)
def _load_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _build_language(raw_language: Any) -> Any:
    if _TSLanguage is None:
        return raw_language
    if isinstance(raw_language, _TSLanguage):
        return raw_language
    try:
        return _TSLanguage(raw_language)  # type: ignore[call-arg]
    except Exception:
        return raw_language


@lru_cache(maxsize=64)
def get_language(language: Language) -> Any | None:
    spec = _GRAMMARS.get(language)
    if spec is None:
        return None

    try:
        module = _load_module(spec.module_name)
    except Exception:
        return None

    for callable_name in spec.callables:
        loader = getattr(module, callable_name, None)
        if callable(loader):
            try:
                return _build_language(loader())
            except Exception:
                continue
    return None


def _new_parser(lang_obj: Any) -> Any:
    if _TSParser is None:
        return None

    try:
        parser = _TSParser()
    except Exception:
        try:
            parser = _TSParser(lang_obj)  # type: ignore[call-arg]
            return parser
        except Exception:
            return None

    for setter in ("set_language", "language"):
        try:
            attr = getattr(parser, setter)
            if callable(attr):
                attr(lang_obj)
            else:
                setattr(parser, setter, lang_obj)
            return parser
        except Exception:
            continue

    return None


@lru_cache(maxsize=64)
def get_parser(language: Language) -> Any | None:
    lang_obj = get_language(language)
    if lang_obj is None:
        return None

    with _LOCK:
        return _new_parser(lang_obj)


def is_supported_code_language(language: Language) -> bool:
    return language in _GRAMMARS
