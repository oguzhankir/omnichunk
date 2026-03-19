from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from threading import RLock
from typing import Any

from omnichunk.types import Language

_tree_sitter: Any | None
try:
    import tree_sitter as _tree_sitter_mod

    _tree_sitter = _tree_sitter_mod
except Exception:  # pragma: no cover
    _tree_sitter = None

_TSLanguage: Any | None = (
    getattr(_tree_sitter, "Language", None) if _tree_sitter is not None else None
)
_TSParser: Any | None = getattr(_tree_sitter, "Parser", None) if _tree_sitter is not None else None


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
        language_ctor: Any = _TSLanguage
        return language_ctor(raw_language)
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
        parser_ctor: Any = _TSParser
        parser = parser_ctor()
    except Exception:
        try:
            parser_ctor_with_lang: Any = _TSParser
            parser = parser_ctor_with_lang(lang_obj)
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
