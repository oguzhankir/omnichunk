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


def _has_tree_sitter_bash() -> bool:
    try:
        __import__("tree_sitter_bash")
    except ImportError:
        return False
    return True


skip_if_no_bash = pytest.mark.skipif(
    not _has_tree_sitter_bash(), reason="tree-sitter-bash not installed"
)


@skip_if_no_bash
def test_bash_chunking_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "bash_complex.sh").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "deploy.sh", code
    )
    assert chunks
    assert "".join(c.text for c in chunks) == code
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


@skip_if_no_bash
def test_bash_function_entities(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "bash_complex.sh").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "deploy.sh", code
    )
    fn_names = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "function"
    }
    assert {"deploy", "main", "usage"} <= fn_names


@skip_if_no_bash
def test_bash_heredocs_never_split(fixtures_dir: Path) -> None:
    """No chunk may contain an opening <<MARKER without the closing MARKER."""
    import re as _re

    code = (fixtures_dir / "bash_complex.sh").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "deploy.sh", code
    )
    for ch in chunks:
        markers = _re.findall(r"<<\-?\s*(\w+)", ch.text)
        for marker in markers:
            # Closing marker appears at line start in the same chunk
            assert _re.search(rf"^\s*{marker}\s*$", ch.text, _re.MULTILINE), (
                f"heredoc marker {marker!r} opened but not closed in chunk: {ch.text[:80]!r}"
            )


@skip_if_no_bash
def test_bash_extension_variants_routed(tmp_path: Path) -> None:
    """All four bash-family extensions route to the bash language."""
    chunker = Chunker(max_chunk_size=200, min_chunk_size=10, size_unit="chars")
    for ext in (".sh", ".bash", ".zsh", ".fish"):
        chunks = chunker.chunk(f"script{ext}", "echo hello\n")
        assert chunks[0].context.language == "bash"


def _has_grammar(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


skip_if_no_scala = pytest.mark.skipif(
    not _has_grammar("tree_sitter_scala"), reason="tree-sitter-scala not installed"
)
skip_if_no_elixir = pytest.mark.skipif(
    not _has_grammar("tree_sitter_elixir"), reason="tree-sitter-elixir not installed"
)


@pytest.mark.parametrize(
    ("filepath", "fixture", "expected_language", "expected_kinds"),
    [
        ("hello.scala", "scala_complex.scala", "scala", {"class", "interface", "function"}),
        ("calc.ex", "elixir_complex.ex", "elixir", {"class", "function", "macro"}),
    ],
)
def test_scala_elixir_chunking(
    filepath: str,
    fixture: str,
    expected_language: str,
    expected_kinds: set[str],
    fixtures_dir: Path,
) -> None:
    if expected_language == "scala" and not _has_grammar("tree_sitter_scala"):
        pytest.skip("tree-sitter-scala not installed")
    if expected_language == "elixir" and not _has_grammar("tree_sitter_elixir"):
        pytest.skip("tree-sitter-elixir not installed")

    code = (fixtures_dir / fixture).read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars")
    chunks = chunker.chunk(filepath, code)
    assert chunks
    assert "".join(c.text for c in chunks) == code
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start
    assert chunks[0].context.language == expected_language

    kinds = {e.type.value for c in chunks for e in c.context.entities}
    assert expected_kinds <= kinds, f"missing kinds: {expected_kinds - kinds} in {kinds}"


@skip_if_no_scala
def test_scala_nested_object_detected(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "scala_complex.scala").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "hello.scala", code
    )
    names = {e.name for c in chunks for e in c.context.entities}
    # Nested Hello.Inner object must be visible alongside top-level Hello/Math.
    assert {"Hello", "Inner", "Math"} <= names


@skip_if_no_elixir
def test_elixir_defmodule_name_captured(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "elixir_complex.ex").read_text(encoding="utf-8")
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "calc.ex", code
    )
    class_names = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "class"
    }
    assert "Inventory" in class_names
    assert "Inventory.Item" in class_names


@skip_if_no_sql
def test_sql_at_least_one_complete_statement_per_chunk(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "sql_complex.sql").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=500, min_chunk_size=20, size_unit="chars")
    chunks = chunker.chunk("schema.sql", code)
    # Every chunk should contain at least one semicolon (statement terminator)
    # OR be the only chunk (degenerate small-file case).
    for ch in chunks:
        assert ";" in ch.text, f"chunk has no statement boundary: {ch.text[:80]!r}"
