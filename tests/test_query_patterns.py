from __future__ import annotations

from omnichunk.parser.query_patterns import get_query_source

_LANGUAGES_WITH_NAME_CAPTURES = [
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "c",
    "cpp",
    "csharp",
    "ruby",
    "php",
    "kotlin",
    "swift",
]


def test_query_source_exists_for_python() -> None:
    source = get_query_source("python")
    assert source is not None
    assert "function_definition" in source
    assert "class_definition" in source
    assert "@name" in source


def test_query_source_missing_for_plaintext() -> None:
    assert get_query_source("plaintext") is None


def test_query_source_exists_for_extended_languages() -> None:
    for language in ["c", "cpp", "csharp", "ruby", "php", "kotlin", "swift"]:
        source = get_query_source(language)  # type: ignore[arg-type]
        assert source is not None
        assert "@entity" in source


def test_query_sources_include_name_captures_for_supported_languages() -> None:
    for language in _LANGUAGES_WITH_NAME_CAPTURES:
        source = get_query_source(language)  # type: ignore[arg-type]
        assert source is not None
        assert "@name" in source
