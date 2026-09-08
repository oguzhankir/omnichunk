from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from omnichunk import Chunker
from omnichunk.context import entities
from omnichunk.parser.tree_sitter import parse_code
from omnichunk.types import ByteRange, EntityInfo, EntityType


@dataclass
class PluginNode:
    type: str
    start_byte: int
    end_byte: int
    children: list[Any] = field(default_factory=list)
    parent: Any = None
    start_point: tuple[int, int] = (0, 0)
    end_point: tuple[int, int] = (0, 0)


def plugin_tree(source: str, node_type: str) -> SimpleNamespace:
    node = PluginNode(node_type, 0, len(source.encode()))
    root = PluginNode("root", 0, node.end_byte, children=[node])
    node.parent = root
    return SimpleNamespace(root_node=root)


@pytest.mark.parametrize(
    "language,node_type,source,name",
    [
        ("python", "function_definition", "def example(x: dict[str, int]): return x", "example"),
        ("python", "class_definition", "class Example: pass", "Example"),
        ("javascript", "function_declaration", "function example() { return 1; }", "example"),
        ("typescript", "interface_declaration", "interface Example { id: string; }", "Example"),
        ("rust", "function_item", "fn example<T>() where T: Clone {}", "example"),
        ("go", "function_declaration", "func example() {}", "example"),
        ("java", "class_declaration", "class Example {}", "Example"),
        ("kotlin", "function_declaration", "fun example() = 1", "example"),
        ("swift", "function_declaration", "func example() {}", "example"),
        ("bash", "function_definition", "example() { :; }", "example"),
    ],
)
def test_plugin_ast_without_grammar_fields_extracts_declarations(
    monkeypatch: pytest.MonkeyPatch, language: str, node_type: str, source: str, name: str
) -> None:
    monkeypatch.setattr(entities, "_compile_query", lambda *args: None)
    found = entities.extract_entities(source, language, plugin_tree(source, node_type))
    assert [item.name for item in found] == [name]
    assert found[0].byte_range == ByteRange(0, len(source.encode()))
    assert found[0].signature


@pytest.mark.parametrize("capture_shape", ["dict", "names", "indexes", "legacy_cursor"])
def test_query_api_variants_preserve_unicode_names_and_deduplicate(
    monkeypatch: pytest.MonkeyPatch, capture_shape: str
) -> None:
    source = "def café(): pass"
    tree = plugin_tree(source, "function_definition")
    declaration = tree.root_node.children[0]
    name = PluginNode("identifier", 4, len("def café".encode()), parent=declaration)
    pairs = [(declaration, "entity.function"), (name, "name"), (declaration, "entity.function")]
    query = SimpleNamespace(capture_names=["entity.function", "name"])
    if capture_shape == "dict":
        raw = {"entity.function": [declaration, declaration], "name": (name,), "invalid": object()}
    elif capture_shape == "indexes":
        raw = [(declaration, 0), (name, 1), (declaration, 0), (name, 99), None, (name,)]
    else:
        raw = [*pairs, (name, "unknown.capture")]
    if capture_shape == "legacy_cursor":

        class Cursor:
            def __init__(self, query: object):
                pass

            def captures(self, query: object, root: object) -> object:
                return raw

        monkeypatch.setattr(entities, "_TSQueryCursor", Cursor)
    else:
        query.captures = lambda root: raw
    monkeypatch.setattr(entities, "_compile_query", lambda *args: query)
    found = entities.extract_entities(source, "python", tree)
    assert len(found) == 1
    assert found[0].name == "café"
    assert found[0].signature == "def café():"


def test_broken_query_and_cursor_fall_back_to_ast(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object) -> object:
        raise RuntimeError("incompatible query ABI")

    monkeypatch.setattr(entities, "_compile_query", lambda *args: SimpleNamespace(captures=broken))
    monkeypatch.setattr(entities, "_TSQueryCursor", broken)
    source = "class Example: pass"
    found = entities.extract_entities(source, "python", plugin_tree(source, "class_definition"))
    assert [item.name for item in found] == ["Example"]


def test_query_name_ancestry_uses_tree_sitter_node_equality() -> None:
    parsed = parse_code("class Example:\n    pass\n", "python")
    if parsed.tree is None:
        pytest.skip("Python grammar not installed")
    declaration = parsed.tree.root_node.named_children[0]
    name = declaration.child_by_field_name("name")
    assert name is not None
    equivalent = parsed.tree.root_node.named_children[0]
    assert declaration == equivalent
    assert entities._distance_to_ancestor(name, equivalent) == 1


def test_query_compilation_uses_legacy_grammar_method(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object) -> object:
        raise ValueError("new Query API unavailable")

    compiled = object()
    monkeypatch.setattr(entities, "_TSQuery", broken)
    monkeypatch.setattr(
        entities, "get_language", lambda language: SimpleNamespace(query=lambda _: compiled)
    )
    entities._compile_query_cached.cache_clear()
    try:
        assert entities._compile_query("python", "fixture") is compiled
        monkeypatch.setattr(
            entities, "get_language", lambda language: SimpleNamespace(query=broken)
        )
        entities._compile_query_cached.cache_clear()
        assert entities._compile_query("python", "fixture") is None
    finally:
        entities._compile_query_cached.cache_clear()


@pytest.mark.parametrize(
    "language,node_type,source,expected",
    [
        ("python", "import_from_statement", "from pkg import *, item as alias,", {"pkg", "alias"}),
        ("python", "import_statement", "import package.module,", {"package"}),
        ("javascript", "import_statement", 'import * as ns from "module";', {"ns"}),
        ("typescript", "import_statement", 'import { item as alias, } from "module";', {"alias"}),
        (
            "rust",
            "use_declaration",
            "pub use crate::{self, io::{Read, Write as W}};",
            {"crate", "Read", "W"},
        ),
        (
            "go",
            "import_declaration",
            'import (\n// packages\n_ "net/http"\n. "fmt"\nx "pkg/x"\n) ',
            {"http", "fmt", "x"},
        ),
        ("java", "import_declaration", "import static java.util.Collections.*;", {"Collections"}),
        ("c", "preproc_include", '#include "module.h"', {"include"}),
        ("kotlin", "import_header", "import example.Widget", {"import"}),
        ("python", "import_statement", "import ?", {"?"}),
    ],
)
def test_import_extraction_fallbacks_keep_aliases_and_source_ranges(
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    node_type: str,
    source: str,
    expected: set[str],
) -> None:
    monkeypatch.setattr(entities, "_compile_query", lambda *args: None)
    found = entities.extract_entities(source, language, plugin_tree(source, node_type))
    assert {item.name for item in found} == expected
    assert all(item.type == EntityType.IMPORT for item in found)
    assert all(item.byte_range == ByteRange(0, len(source.encode())) for item in found)


@pytest.mark.parametrize(
    "source,expected",
    [
        ('def f():\n    "a" "b"\n    pass\n', "ab"),
        ('def f():\n    ""\n    pass\n', None),
        ('def f():\n    f"value {1}"\n', None),
        ('def f():\n    b"bytes"\n', None),
        ("def f():\n    123\n", None),
        ('def f():\n    return "value"\n', None),
    ],
)
def test_python_docstrings_reject_nonliteral_or_nonstring_expressions(
    source: str, expected: str | None
) -> None:
    tree = parse_code(source, "python").tree
    found = entities.extract_entities(source, "python", tree)
    assert next(item for item in found if item.name == "f").docstring == expected


@pytest.mark.parametrize(
    "language,source,name,expected",
    [
        ("javascript", "/**\n * Türkçe docs\n */\nfunction f() {}", "f", "Türkçe docs"),
        ("rust", "/// First\n//! Second\nfn f() {}", "f", "First\nSecond"),
        ("go", "package main\n// First\n// Second\nfunc f() {}", "f", "First\nSecond"),
        ("javascript", "/** */\nfunction f() {}", "f", None),
        ("javascript", "/** other */\nconst x = 1;\nfunction f() {}", "f", None),
    ],
)
def test_adjacent_documentation_comments_respect_statement_boundaries(
    language: str, source: str, name: str, expected: str | None
) -> None:
    parsed = parse_code(source, language)
    if parsed.tree is None:
        pytest.skip(f"{language} grammar not installed")
    found = entities.extract_entities(source, language, parsed.tree)
    assert next(item for item in found if item.name == name).docstring == expected


def test_parent_enrichment_keeps_explicit_parent_and_unlocated_metadata() -> None:
    outer = EntityInfo("Outer", EntityType.CLASS, byte_range=ByteRange(0, 100))
    inner = EntityInfo(
        "inner", EntityType.FUNCTION, byte_range=ByteRange(20, 40), parent="explicit"
    )
    orphan = EntityInfo("external", EntityType.MODULE)
    found = entities.enrich_parent_links([inner, orphan, outer])
    assert next(item for item in found if item.name == "inner").parent == "explicit"
    assert orphan in found


def test_code_context_variants_filter_imports_and_sibling_signatures() -> None:
    source = (
        "from useful import Useful\nfrom unused import Unused\n\n"
        "def first(value: Useful):\n    return value\n\n"
        "def second():\n    return 2\n\n"
        "def third():\n    return 3\n"
    )
    chunker = Chunker(max_chunk_size=65, min_chunk_size=1, overflow_policy="preserve")
    full = chunker.chunk("example.py", source, filter_imports=True, sibling_detail="names")
    first = next(
        chunk for chunk in full if any(item.name == "first" for item in chunk.context.entities)
    )
    assert all(item.signature == "" for chunk in full for item in chunk.context.siblings)
    assert all(item.name != "Unused" for item in first.context.imports)
    minimal = chunker.chunk("example.py", source, context_mode="minimal", include_imports=False)
    assert all(not chunk.context.entities and not chunk.context.imports for chunk in minimal)


@pytest.mark.parametrize(
    "path,source",
    [
        ("data.json", '{"quote": "a\\"b", "nested": [{"x": 1}], "tail": true}'),
        ("data.json", "[1, 2, 3]"),
        ("data.json", "{}"),
        ("data.json", '{"broken": [1, 2'),
        ("data.yaml", "- one\n- two\n"),
        ("data.toml", 'key = "öğe"\n'),
        ("data.html", "Text without elements 你好"),
        ("data.xml", "<item>Türkçe</item>"),
    ],
)
def test_markup_heuristic_fallbacks_preserve_exact_source(path: str, source: str) -> None:
    chunker = Chunker(
        max_chunk_size=24, min_chunk_size=1, context_mode="none", coverage_policy="lossless"
    )
    chunks = chunker.chunk(path, source)
    assert "".join(chunk.text for chunk in chunks) == source
    assert all(len(chunk.contextualized_text) <= 24 for chunk in chunks)
    assert chunks == chunker.chunk(path, source)
