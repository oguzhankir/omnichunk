from __future__ import annotations

import json

import pytest

from omnichunk import Chunker
from omnichunk.formats.chunk import chunk_loaded_document
from omnichunk.formats.ipynb import load_ipynb
from omnichunk.parser import tree_sitter
from omnichunk.types import ChunkingError, ChunkOptions


def _assert_entity_coordinates(chunks, source: str) -> None:
    raw = source.encode("utf-8")
    for chunk in chunks:
        for entity in [*chunk.context.entities, *chunk.context.scope]:
            if entity.byte_range is None:
                continue
            start, end = entity.byte_range.start, entity.byte_range.end
            assert 0 <= start < end <= len(raw)
            text = raw[start:end].decode("utf-8")
            if entity.name not in {"paragraph", "section", "code_block", "heading"}:
                assert entity.name in text
            if entity.line_range is not None:
                assert entity.line_range.start == raw[:start].count(b"\n")
                assert entity.line_range.end == raw[: max(start, end - 1)].count(b"\n")


@pytest.mark.parametrize("suffix", ["md", "txt"])
def test_prose_entity_ranges_are_utf8_bytes(suffix: str) -> None:
    text = "Türkçe başlık\n\n你好 dünya.\n\nSon paragraf.\n"
    chunks = Chunker(max_chunk_size=30, min_chunk_size=1, size_unit="chars").chunk(
        f"source.{suffix}", text
    )
    assert "".join(c.text for c in chunks) == text
    for chunk in chunks:
        assert all(entity.byte_range == chunk.byte_range for entity in chunk.context.entities)
    _assert_entity_coordinates(chunks, text)


def test_notebook_rebases_nested_entities_and_scopes() -> None:
    notebook = json.dumps(
        {
            "cells": [
                {"cell_type": "markdown", "source": "# Türkçe 你好\n\n"},
                {
                    "cell_type": "code",
                    "source": "class Kutu:\n    def oku(self):\n        return 1\n",
                },
            ]
        }
    )
    loaded = load_ipynb(notebook)
    chunks = Chunker(max_chunk_size=200, min_chunk_size=1, size_unit="chars").chunk(
        "source.ipynb", notebook
    )
    assert "".join(c.text for c in chunks) == loaded.text
    _assert_entity_coordinates(chunks, loaded.text)


def test_hybrid_rebases_nested_entities_and_scopes() -> None:
    source = (
        '# %% [markdown]\n"""Türkçe 你好"""\n# %%\n'
        "class Kutu:\n    def oku(self):\n        return 1\n"
    )
    chunks = Chunker(max_chunk_size=200, min_chunk_size=1, size_unit="chars").chunk(
        "source.py", source
    )
    assert "".join(c.text for c in chunks) == source
    _assert_entity_coordinates(chunks, source)


def test_markdown_mixed_fences_rebase_code_context() -> None:
    source = (
        "# Türkçe 你好\n\n```python\nclass Kutu:\n    def oku(self):\n        return 1\n```\n"
        '\n```json\n{"merhaba": "dünya"}\n```\n'
    )
    chunks = Chunker(max_chunk_size=250, min_chunk_size=1, size_unit="chars").chunk(
        "source.md", source
    )
    assert "".join(c.text for c in chunks) == source
    _assert_entity_coordinates(chunks, source)
    assert {c.context.language for c in chunks} >= {"python", "json"}


@pytest.mark.parametrize("fence", ["```", "~~~~", "````"])
def test_code_fence_comments_do_not_become_markdown_headings(fence: str) -> None:
    source = (
        f"# Real heading\n\n{fence}python\n# A code comment\n"
        f"def oku():\n    return 1\n{fence}\n\nAfter.\n"
    )
    chunks = Chunker(max_chunk_size=300, min_chunk_size=1, size_unit="chars").chunk(
        "source.md", source
    )
    assert "".join(c.text for c in chunks) == source
    code_chunks = [c for c in chunks if c.context.language == "python"]
    assert code_chunks
    assert all(c.context.heading_hierarchy == ["Real heading"] for c in code_chunks)
    assert all("A code comment" not in c.context.heading_hierarchy for c in chunks)
    _assert_entity_coordinates(chunks, source)


@pytest.mark.parametrize("source", ["invalid JSON", "[]", '{"cells": null}'])
def test_malformed_notebooks_fail_with_loader_diagnostic(source: str) -> None:
    loaded = load_ipynb(source)
    assert loaded.warnings
    with pytest.raises(ChunkingError, match="ipynb"):
        chunk_loaded_document("bad.ipynb", loaded, ChunkOptions(size_unit="chars"))


def test_nonfatal_loader_warnings_reach_chunk_context() -> None:
    source = json.dumps(
        {
            "cells": [
                {"cell_type": "unknown", "source": "ignored"},
                {"cell_type": "markdown", "source": "Usable source."},
            ]
        }
    )
    chunks = Chunker(size_unit="chars").chunk("source.ipynb", source)
    assert chunks
    assert all("unknown_cell_type:unknown" in " ".join(c.context.parse_errors) for c in chunks)


def test_python_regex_fallback_has_utf8_entity_ranges(monkeypatch) -> None:
    monkeypatch.setattr(tree_sitter, "get_ts_parser", lambda language: None)
    source = '# Türkçe 你好\n\ndef oku():\n    return "dünya"\n'
    chunks = Chunker(max_chunk_size=200, size_unit="chars").chunk("source.py", source)
    _assert_entity_coordinates(chunks, source)
    assert all(c.context.parse_errors for c in chunks)


def test_failed_plugin_falls_back_to_builtin_with_diagnostic(monkeypatch) -> None:
    import omnichunk.plugins

    def broken(filepath: str, source: str):
        raise RuntimeError("parser unavailable")

    monkeypatch.setattr(omnichunk.plugins, "get_parser", lambda language: broken)
    result = tree_sitter.parse_code("def oku():\n    return 1\n", "python")
    assert result.tree is not None
    assert any("Plugin parser failed" in error for error in result.errors)


def test_capability_matrix_distinguishes_detection_and_installed_grammar(monkeypatch) -> None:
    from omnichunk.parser import languages

    monkeypatch.setattr(languages, "get_language", lambda language: None)
    capabilities = languages.language_capabilities()
    rows = {item.language: item for item in capabilities}
    assert list(rows) == sorted(rows)
    assert ".py" in rows["python"].extensions
    assert rows["python"].grammar_registered
    assert not rows["python"].grammar_available
    assert rows["python"].extraction == "regex"
    assert ".hs" in rows["haskell"].extensions
    assert not rows["haskell"].grammar_registered
    assert rows["haskell"].extraction == "none"


def test_decorators_and_nested_generics_keep_source_metadata() -> None:
    source = (
        "# Türkçe comment\n@deco\nclass Kutu[T]:\n"
        '    """A documented generic box."""\n'
        "    @staticmethod\n    def oku[U](item: U) -> U:\n        return item\n"
    )
    chunks = Chunker(max_chunk_size=500, size_unit="chars").chunk("source.py", source)
    _assert_entity_coordinates(chunks, source)
    entities = [entity for c in chunks for entity in c.context.entities]
    cls = next(entity for entity in entities if entity.name == "Kutu")
    method = next(entity for entity in entities if entity.name == "oku")
    assert source.encode()[cls.byte_range.start : cls.byte_range.end].startswith(b"@deco")
    assert method.parent == "Kutu"
    assert source.encode()[method.byte_range.start : method.byte_range.end].startswith(
        b"@staticmethod"
    )


def test_entity_sweep_retains_outer_scopes_without_scanning_expired_entities() -> None:
    from omnichunk.context.range_index import EntityRangeSweep
    from omnichunk.types import ByteRange, EntityInfo, EntityType

    entities = [EntityInfo("outer", EntityType.CLASS, byte_range=ByteRange(0, 1000))]
    entities.extend(
        EntityInfo(f"f{i}", EntityType.FUNCTION, byte_range=ByteRange(i * 10, i * 10 + 8))
        for i in range(100)
    )
    sweep = EntityRangeSweep(entities)
    for i in range(100):
        assert [e.name for e in sweep.overlapping(ByteRange(i * 10, (i + 1) * 10))] == [
            "outer",
            f"f{i}",
        ]
    assert sweep.overlapping(ByteRange(1000, 1010)) == []
    with pytest.raises(ValueError, match="source order"):
        sweep.overlapping(ByteRange(0, 10))
