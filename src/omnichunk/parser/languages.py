from __future__ import annotations

import importlib
from dataclasses import dataclass
from functools import lru_cache
from threading import RLock, local
from typing import Any, Literal

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


@dataclass(frozen=True)
class LanguageCapability:
    """Code-language support in this environment, independently of filename detection."""

    language: Language
    extensions: tuple[str, ...]
    grammar_registered: bool
    grammar_available: bool
    parser_available: bool
    query_available: bool
    extraction: Literal["ast", "regex", "none"]
    grammar_module: str | None = None


def language_capabilities() -> tuple[LanguageCapability, ...]:
    """Return the deterministic code-language matrix for installed optional grammars.

    ``query_available`` reports a bundled query, not exhaustive syntax coverage.
    ``grammar_available`` means the grammar loaded, while ``parser_available``
    also verifies parser construction. Input syntax diagnostics remain in context.
    """
    from omnichunk.parser.query_patterns import get_query_source
    from omnichunk.util.detect import _CODE_LANGUAGES, _EXTENSION_LANGUAGE

    rows: list[LanguageCapability] = []
    for language in sorted(_CODE_LANGUAGES):
        grammar = _GRAMMARS.get(language)
        available = grammar is not None and get_language(language) is not None
        parser_available = available and get_parser(language) is not None
        rows.append(
            LanguageCapability(
                language=language,
                extensions=tuple(
                    sorted(
                        extension
                        for extension, detected in _EXTENSION_LANGUAGE.items()
                        if detected == language
                    )
                ),
                grammar_registered=grammar is not None,
                grammar_available=available,
                parser_available=parser_available,
                query_available=get_query_source(language) is not None,
                extraction="ast"
                if parser_available
                else "regex"
                if language == "python"
                else "none",
                grammar_module=grammar.module_name if grammar else None,
            )
        )
    return tuple(rows)


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
    "sql": GrammarSpec("tree_sitter_sql", ("language",)),
    "bash": GrammarSpec("tree_sitter_bash", ("language",)),
    "scala": GrammarSpec("tree_sitter_scala", ("language",)),
    "elixir": GrammarSpec("tree_sitter_elixir", ("language",)),
}

_LOCK = RLock()
_THREAD_LOCAL = local()


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


def get_parser(language: Language) -> Any | None:
    lang_obj = get_language(language)
    if lang_obj is None:
        return None

    parser_cache = getattr(_THREAD_LOCAL, "parsers", None)
    if parser_cache is None:
        parser_cache = {}
        _THREAD_LOCAL.parsers = parser_cache

    cached = parser_cache.get(language)
    if cached is not None:
        return cached

    with _LOCK:
        parser = _new_parser(lang_obj)

    if parser is not None:
        parser_cache[language] = parser

    return parser


def is_supported_code_language(language: Language) -> bool:
    return language in _GRAMMARS
