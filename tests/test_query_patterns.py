from __future__ import annotations

from omnichunk.parser.query_patterns import get_query_source


def test_query_source_exists_for_python() -> None:
    source = get_query_source("python")
    assert source is not None
    assert "function_definition" in source
    assert "class_definition" in source


def test_query_source_missing_for_plaintext() -> None:
    assert get_query_source("plaintext") is None


def test_query_source_exists_for_extended_languages() -> None:
    for language in ["c", "cpp", "csharp", "ruby", "php", "kotlin", "swift"]:
        source = get_query_source(language)  # type: ignore[arg-type]
        assert source is not None
        assert "@entity" in source
