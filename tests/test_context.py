from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker
from omnichunk.context import entities as entities_mod


class _FakeNode:
    def __init__(
        self,
        node_type: str,
        start: int,
        end: int,
        *,
        children: list[_FakeNode] | None = None,
        fields: dict[str, _FakeNode] | None = None,
        is_named: bool = True,
    ) -> None:
        self.type = node_type
        self.start_byte = start
        self.end_byte = end
        self.start_point = (0, 0)
        self.end_point = (0, 0)
        self.children = children or []
        self.named_children = [
            child for child in self.children if getattr(child, "is_named", True)
        ]
        self._fields = fields or {}
        self.is_named = is_named
        self.parent: _FakeNode | None = None

        for child in self.children:
            child.parent = self
        for child in self._fields.values():
            child.parent = self

    def child_by_field_name(self, field_name: str) -> _FakeNode | None:
        return self._fields.get(field_name)


def test_contextualized_text_contains_metadata(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=240, size_unit="chars", context_mode="full")

    chunks = chunker.chunk("src/services/user_service.py", code)

    assert chunks
    sample = chunks[0].contextualized_text
    assert "# src/services/user_service.py" in sample
    assert "# Language: python" in sample


def test_import_tracking_and_siblings() -> None:
    code = (
        "import os\n"
        "import json\n\n"
        "def a():\n    return os.getcwd()\n\n"
        "def b():\n    return json.dumps({})\n\n"
        "def c():\n    return 3\n"
    )
    chunker = Chunker(max_chunk_size=55, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("imports.py", code)

    assert chunks
    assert any(c.context.imports for c in chunks)
    assert any(c.context.siblings for c in chunks)


def test_filter_imports_option() -> None:
    code = "import os\nimport json\n\ndef a():\n    return os.getcwd()\n"
    chunker = Chunker(max_chunk_size=80, size_unit="chars", filter_imports=True)

    chunks = chunker.chunk("imports.py", code)

    assert chunks
    for chunk in chunks:
        if chunk.context.imports:
            names = {imp.name for imp in chunk.context.imports}
            assert names <= {"os", "json"}


def test_siblings_prefer_same_parent_scope() -> None:
    code = (
        "class Service:\n"
        "    def first(self):\n"
        "        return 1\n\n"
        "    def second(self):\n"
        "        return 2\n\n"
        "def standalone():\n"
        "    return 3\n"
    )
    chunker = Chunker(max_chunk_size=35, min_chunk_size=5, size_unit="chars", max_siblings=3)

    chunks = chunker.chunk("scope_siblings.py", code)

    target = next((c for c in chunks if "def second" in c.text), None)
    assert target is not None

    names = {s.name for s in target.context.siblings}
    assert "first" in names


def test_python_entity_signatures_include_full_type_hints() -> None:
    code = (
        "from typing import Optional\n\n"
        "class Service:\n"
        "    def process(self, data: dict, limit: int = 10) -> Optional[str]:\n"
        "        return None\n"
    )
    chunker = Chunker(max_chunk_size=300, size_unit="chars")
    chunks = chunker.chunk("service.py", code)
    all_entities = [e for c in chunks for e in c.context.entities]

    process_entity = next((e for e in all_entities if e.name == "process"), None)
    assert process_entity is not None
    assert "data: dict" in process_entity.signature
    assert "limit: int" in process_entity.signature


def test_python_class_signature_with_bases() -> None:
    code = "class MyService(BaseService, Mixin):\n    pass\n"
    chunker = Chunker(max_chunk_size=200, size_unit="chars")
    chunks = chunker.chunk("svc.py", code)
    all_entities = [e for c in chunks for e in c.context.entities]

    cls = next((e for e in all_entities if e.name == "MyService"), None)
    assert cls is not None
    assert "BaseService" in cls.signature
    assert "Mixin" in cls.signature


def test_python_docstring_requires_first_statement_string() -> None:
    good_source = '"""Actual docstring."""\nreturn 1\n'
    good_literal = _FakeNode("string", 0, len('"""Actual docstring."""'))
    good_stmt = _FakeNode(
        "expression_statement",
        0,
        len('"""Actual docstring."""'),
        children=[good_literal],
    )
    return_stmt = _FakeNode("return_statement", len('"""Actual docstring."""\n'), len(good_source))
    good_body = _FakeNode("block", 0, len(good_source), children=[good_stmt, return_stmt])
    good_func = _FakeNode(
        "function_definition",
        0,
        len(good_source),
        fields={"body": good_body},
    )

    bad_source = 'value = """not a docstring"""\n"""also not a docstring"""\n'
    assignment = _FakeNode("assignment", 0, bad_source.index("\n") + 1)
    trailing_literal = _FakeNode("string", bad_source.index('"""also'), len(bad_source) - 1)
    trailing_stmt = _FakeNode(
        "expression_statement",
        bad_source.index('"""also'),
        len(bad_source),
        children=[trailing_literal],
    )
    bad_body = _FakeNode("block", 0, len(bad_source), children=[assignment, trailing_stmt])
    bad_func = _FakeNode("function_definition", 0, len(bad_source), fields={"body": bad_body})

    assert entities_mod._extract_python_docstring(good_func, good_source.encode("utf-8")) == (
        "Actual docstring."
    )
    assert entities_mod._extract_python_docstring(bad_func, bad_source.encode("utf-8")) is None


def test_javascript_jsdoc_attaches_only_to_adjacent_entity() -> None:
    source = (
        "/** Detached comment */\n"
        "const value = 1;\n\n"
        "/**\n"
        " * Attached to run\n"
        " */\n"
        "function run() {}\n"
        "function noop() {}\n"
    )

    detached_start = source.index("/** Detached comment */")
    detached_end = detached_start + len("/** Detached comment */")
    const_start = source.index("const value")
    const_end = source.index(";", const_start) + 1
    attached_start = source.index("/**\n")
    attached_end = source.index("*/", attached_start) + 2
    run_start = source.index("function run")
    run_end = source.index("}\n", run_start) + 1
    noop_start = source.index("function noop")
    noop_end = source.rindex("}") + 1

    detached_comment = _FakeNode("comment", detached_start, detached_end)
    const_decl = _FakeNode("lexical_declaration", const_start, const_end)
    attached_comment = _FakeNode("comment", attached_start, attached_end)
    run_func = _FakeNode("function_declaration", run_start, run_end)
    noop_func = _FakeNode("function_declaration", noop_start, noop_end)

    _FakeNode(
        "program",
        0,
        len(source),
        children=[detached_comment, const_decl, attached_comment, run_func, noop_func],
    )

    doc = entities_mod._extract_leading_comment(run_func, source.encode("utf-8"))
    assert doc == "Attached to run"
    assert entities_mod._extract_leading_comment(noop_func, source.encode("utf-8")) is None


def test_rust_grouped_imports_expand_to_individual_items() -> None:
    imports_one = entities_mod._parse_rust_imports("use std::collections::{HashMap, HashSet};")
    imports_two = entities_mod._parse_rust_imports(
        "use crate::net::{self, client::Client as HttpClient};"
    )
    import_names = {name for name, _ in [*imports_one, *imports_two]}

    assert {"HashMap", "HashSet", "net", "HttpClient"} <= import_names


def test_go_import_block_parses_each_import_spec() -> None:
    code = (
        "package main\n\n"
        "import (\n"
        '    "fmt"\n'
        '    osalias "os"\n'
        ")\n\n"
        "func main() {\n"
        "    fmt.Println(osalias.Args)\n"
        "}\n"
    )

    parsed = entities_mod._parse_go_imports(code)
    import_names = {name for name, _ in parsed}

    assert {"fmt", "osalias"} <= import_names


def test_java_imports_include_static_and_non_static_symbols() -> None:
    code = (
        "import java.util.List;\n"
        "import static java.lang.Math.max;\n\n"
        "public class Main {\n"
        "    int clamp(int v) {\n"
        "        return max(v, 0);\n"
        "    }\n"
        "}\n"
    )

    parsed = entities_mod._parse_java_imports(code)
    import_names = {name for name, _ in parsed}

    assert {"List", "max"} <= import_names
