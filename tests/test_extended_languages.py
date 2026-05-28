from __future__ import annotations

from pathlib import Path

import pytest

from omnichunk import Chunker


def _has_all_language_modules() -> bool:
    mods = (
        "tree_sitter_c",
        "tree_sitter_cpp",
        "tree_sitter_c_sharp",
        "tree_sitter_ruby",
        "tree_sitter_php",
        "tree_sitter_kotlin",
    )
    for name in mods:
        try:
            __import__(name)
        except ImportError:
            return False
    return True


skip_if_no_extra = pytest.mark.skipif(
    not _has_all_language_modules(),
    reason="all-languages grammars not installed",
)


@skip_if_no_extra
@pytest.mark.parametrize(
    ("filepath", "fixture_name"),
    [
        ("example.c", "c_complex.c"),
        ("example.cpp", "cpp_complex.cpp"),
        ("example.cs", "csharp_complex.cs"),
        ("example.rb", "ruby_complex.rb"),
        ("example.php", "php_complex.php"),
        ("example.kt", "kotlin_complex.kt"),
    ],
)
def test_extended_language_reconstruction(
    filepath: str, fixture_name: str, fixtures_dir: Path
) -> None:
    code = (fixtures_dir / fixture_name).read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=256, min_chunk_size=40, size_unit="chars")
    chunks = chunker.chunk(filepath, code)
    assert chunks
    assert "".join(c.text for c in chunks) == code
    raw = code.encode("utf-8")
    for ch in chunks:
        assert raw[ch.byte_range.start : ch.byte_range.end].decode("utf-8") == ch.text
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


@skip_if_no_extra
@pytest.mark.parametrize(
    ("filepath", "fixture_name", "expected_entity"),
    [
        ("example.c", "c_complex.c", "function"),
        ("example.cpp", "cpp_complex.cpp", "class"),
        ("example.cs", "csharp_complex.cs", "class"),
        ("example.rb", "ruby_complex.rb", "class"),
        ("example.php", "php_complex.php", "class"),
        ("example.kt", "kotlin_complex.kt", "class"),
    ],
)
def test_extended_language_entities(
    filepath: str, fixture_name: str, expected_entity: str, fixtures_dir: Path
) -> None:
    code = (fixtures_dir / fixture_name).read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=256, min_chunk_size=40, size_unit="chars")
    chunks = chunker.chunk(filepath, code)
    all_entity_types = {e.type.value for c in chunks for e in c.context.entities}
    assert any(expected_entity in t for t in all_entity_types), (
        f"Expected entity type containing {expected_entity!r} in {all_entity_types}"
    )


def _has_tree_sitter_sql() -> bool:
    try:
        __import__("tree_sitter_sql")
    except ImportError:
        return False
    return True


skip_if_no_sql = pytest.mark.skipif(
    not _has_tree_sitter_sql(), reason="tree-sitter-sql not installed"
)


@skip_if_no_sql
def test_sql_chunking_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sql_complex.sql").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=500, min_chunk_size=20, size_unit="chars")
    chunks = chunker.chunk("schema.sql", code)
    assert chunks
    assert "".join(c.text for c in chunks) == code
    raw = code.encode("utf-8")
    for ch in chunks:
        assert raw[ch.byte_range.start : ch.byte_range.end].decode("utf-8") == ch.text
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start
    assert chunks[0].context.language == "sql"


@skip_if_no_sql
def test_sql_entities_extracted(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sql_complex.sql").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=500, min_chunk_size=20, size_unit="chars")
    chunks = chunker.chunk("schema.sql", code)
    entities = [(e.name, e.type.value) for c in chunks for e in c.context.entities]
    names = {n for n, _ in entities}
    types = {t for _, t in entities}
    assert "users" in names
    assert "orders" in names
    assert "active_users" in names
    assert "user_lifetime_value" in names
    # All entities should be either sql_object or function (no CLASS/METHOD/etc).
    assert types <= {"sql_object", "function"}, f"unexpected types: {types}"


@skip_if_no_sql
def test_sql_at_least_one_complete_statement_per_chunk(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sql_complex.sql").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=500, min_chunk_size=20, size_unit="chars")
    chunks = chunker.chunk("schema.sql", code)
    # Every chunk should contain at least one semicolon (statement terminator)
    # OR be the only chunk (degenerate small-file case).
    for ch in chunks:
        assert ";" in ch.text, f"chunk has no statement boundary: {ch.text[:80]!r}"
