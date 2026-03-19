from __future__ import annotations

from dataclasses import dataclass

from omnichunk.context.entities import enrich_parent_links, extract_entities
from omnichunk.types import ByteRange, EntityInfo, EntityType, LineRange


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


@dataclass
class _FakeTree:
    root_node: _FakeNode


def _find_span(text: str, snippet: str, *, start: int = 0) -> tuple[int, int]:
    idx = text.index(snippet, start)
    return idx, idx + len(snippet)


def _find_entity(
    entities: list[EntityInfo], *, name: str, entity_type: EntityType
) -> EntityInfo:
    return next(e for e in entities if e.name == name and e.type == entity_type)


def test_extract_entities_rust_names_imports_signatures_and_parent() -> None:
    code = (
        "use std::collections::{HashMap, HashSet};\n"
        "pub struct Config {}\n"
        "impl Config {\n"
        "    pub fn url(&self) -> String { String::new() }\n"
        "}\n"
    )

    import_start, import_end = _find_span(code, "use std::collections::{HashMap, HashSet};")
    struct_start, struct_end = _find_span(code, "pub struct Config {}")
    impl_start, impl_end = _find_span(
        code,
        "impl Config {\n    pub fn url(&self) -> String { String::new() }\n}",
    )
    method_start, method_end = _find_span(code, "pub fn url(&self) -> String { String::new() }")

    struct_name_start, struct_name_end = _find_span(code, "Config", start=struct_start)
    impl_name_start, impl_name_end = _find_span(code, "Config", start=impl_start)
    method_name_start, method_name_end = _find_span(code, "url", start=method_start)

    import_node = _FakeNode("use_declaration", import_start, import_end)
    struct_node = _FakeNode(
        "struct_item",
        struct_start,
        struct_end,
        fields={"name": _FakeNode("identifier", struct_name_start, struct_name_end)},
    )
    method_node = _FakeNode(
        "function_item",
        method_start,
        method_end,
        fields={"name": _FakeNode("identifier", method_name_start, method_name_end)},
    )
    impl_node = _FakeNode(
        "impl_item",
        impl_start,
        impl_end,
        children=[method_node],
        fields={"type": _FakeNode("type_identifier", impl_name_start, impl_name_end)},
    )

    tree = _FakeTree(
        _FakeNode(
            "source_file",
            0,
            len(code),
            children=[import_node, struct_node, impl_node],
        )
    )
    entities = extract_entities(code, "rust", tree)

    import_names = {e.name for e in entities if e.type == EntityType.IMPORT}
    assert {"HashMap", "HashSet"} <= import_names

    _find_entity(entities, name="Config", entity_type=EntityType.CLASS)
    method = _find_entity(entities, name="url", entity_type=EntityType.FUNCTION)
    assert method.parent == "Config"
    assert "pub fn url" in method.signature


def test_extract_entities_go_names_imports_signatures_and_parent() -> None:
    code = (
        "package main\n\n"
        "import (\n"
        '    "fmt"\n'
        '    osalias "os"\n'
        ")\n\n"
        "type Service struct{}\n\n"
        "func (s Service) Run() string {\n"
        "    return fmt.Sprint(osalias.Args)\n"
        "}\n"
    )

    import_start, import_end = _find_span(code, 'import (\n    "fmt"\n    osalias "os"\n)')
    method_start, method_end = _find_span(
        code,
        "func (s Service) Run() string {\n    return fmt.Sprint(osalias.Args)\n}",
    )
    type_start = code.index("type Service struct{}")
    type_end = method_end

    type_name_start, type_name_end = _find_span(code, "Service", start=type_start)
    method_name_start, method_name_end = _find_span(code, "Run", start=method_start)

    import_node = _FakeNode("import_declaration", import_start, import_end)
    method_node = _FakeNode(
        "method_declaration",
        method_start,
        method_end,
        fields={"name": _FakeNode("field_identifier", method_name_start, method_name_end)},
    )
    type_node = _FakeNode(
        "type_declaration",
        type_start,
        type_end,
        children=[method_node],
        fields={"name": _FakeNode("type_identifier", type_name_start, type_name_end)},
    )

    tree = _FakeTree(_FakeNode("source_file", 0, len(code), children=[import_node, type_node]))
    entities = extract_entities(code, "go", tree)

    import_names = {e.name for e in entities if e.type == EntityType.IMPORT}
    assert {"fmt", "osalias"} <= import_names

    _find_entity(entities, name="Service", entity_type=EntityType.TYPE)
    method = _find_entity(entities, name="Run", entity_type=EntityType.METHOD)
    assert method.parent == "Service"
    assert "func (s Service) Run() string" in method.signature


def test_extract_entities_java_names_imports_signatures_and_parent() -> None:
    code = (
        "import java.util.List;\n"
        "import static java.lang.Math.max;\n\n"
        "class Main {\n"
        "    int clamp(int v) {\n"
        "        return max(v, 0);\n"
        "    }\n"
        "}\n"
    )

    import_one_start, import_one_end = _find_span(code, "import java.util.List;")
    import_two_start, import_two_end = _find_span(code, "import static java.lang.Math.max;")
    class_start, class_end = _find_span(
        code,
        "class Main {\n    int clamp(int v) {\n        return max(v, 0);\n    }\n}",
    )
    method_start, method_end = _find_span(
        code,
        "int clamp(int v) {\n        return max(v, 0);\n    }",
    )

    class_name_start, class_name_end = _find_span(code, "Main", start=class_start)
    method_name_start, method_name_end = _find_span(code, "clamp", start=method_start)

    import_node_one = _FakeNode("import_declaration", import_one_start, import_one_end)
    import_node_two = _FakeNode("import_declaration", import_two_start, import_two_end)
    method_node = _FakeNode(
        "method_declaration",
        method_start,
        method_end,
        fields={"name": _FakeNode("identifier", method_name_start, method_name_end)},
    )
    class_node = _FakeNode(
        "class_declaration",
        class_start,
        class_end,
        children=[method_node],
        fields={"name": _FakeNode("identifier", class_name_start, class_name_end)},
    )

    tree = _FakeTree(
        _FakeNode(
            "program",
            0,
            len(code),
            children=[import_node_one, import_node_two, class_node],
        )
    )
    entities = extract_entities(code, "java", tree)

    import_names = {e.name for e in entities if e.type == EntityType.IMPORT}
    assert {"List", "max"} <= import_names

    _find_entity(entities, name="Main", entity_type=EntityType.CLASS)
    method = _find_entity(entities, name="clamp", entity_type=EntityType.METHOD)
    assert method.parent == "Main"
    assert "int clamp(int v)" in method.signature


def test_extract_entities_cpp_names_imports_signatures_and_parent() -> None:
    code = (
        "#include <vector>\n\n"
        "class Service {\n"
        "public:\n"
        "    int run() { return 1; }\n"
        "};\n"
    )

    import_start, import_end = _find_span(code, "#include <vector>")
    class_start, class_end = _find_span(
        code,
        "class Service {\npublic:\n    int run() { return 1; }\n};",
    )
    method_start, method_end = _find_span(code, "int run() { return 1; }")

    class_name_start, class_name_end = _find_span(code, "Service", start=class_start)
    method_decl_start, method_decl_end = _find_span(code, "run()", start=method_start)

    import_node = _FakeNode("preproc_include", import_start, import_end)
    method_node = _FakeNode(
        "function_definition",
        method_start,
        method_end,
        fields={"declarator": _FakeNode("function_declarator", method_decl_start, method_decl_end)},
    )
    class_node = _FakeNode(
        "class_specifier",
        class_start,
        class_end,
        children=[method_node],
        fields={"name": _FakeNode("type_identifier", class_name_start, class_name_end)},
    )

    tree = _FakeTree(
        _FakeNode(
            "translation_unit",
            0,
            len(code),
            children=[import_node, class_node],
        )
    )
    entities = extract_entities(code, "cpp", tree)

    assert any(entity.type == EntityType.IMPORT for entity in entities)

    _find_entity(entities, name="Service", entity_type=EntityType.CLASS)
    method = _find_entity(entities, name="run", entity_type=EntityType.FUNCTION)
    assert method.parent == "Service"
    assert "int run()" in method.signature


def test_extract_entities_c_function_and_import() -> None:
    code = (
        "#include <stdio.h>\n\n"
        "int sum(int a, int b) {\n"
        "    return a + b;\n"
        "}\n"
    )

    import_start, import_end = _find_span(code, "#include <stdio.h>")
    function_start, function_end = _find_span(
        code,
        "int sum(int a, int b) {\n    return a + b;\n}",
    )
    declarator_start, declarator_end = _find_span(code, "sum(int a, int b)", start=function_start)

    import_node = _FakeNode("preproc_include", import_start, import_end)
    function_node = _FakeNode(
        "function_definition",
        function_start,
        function_end,
        fields={"declarator": _FakeNode("function_declarator", declarator_start, declarator_end)},
    )

    tree = _FakeTree(
        _FakeNode(
            "translation_unit",
            0,
            len(code),
            children=[import_node, function_node],
        )
    )
    entities = extract_entities(code, "c", tree)

    assert any(entity.type == EntityType.IMPORT for entity in entities)

    function = _find_entity(entities, name="sum", entity_type=EntityType.FUNCTION)
    assert "int sum(int a, int b)" in function.signature


def test_enrich_parent_links_picks_nearest_container() -> None:
    entities = [
        EntityInfo(
            name="Outer",
            type=EntityType.CLASS,
            byte_range=ByteRange(0, 220),
            line_range=LineRange(0, 20),
        ),
        EntityInfo(
            name="Inner",
            type=EntityType.CLASS,
            byte_range=ByteRange(24, 160),
            line_range=LineRange(2, 16),
        ),
        EntityInfo(
            name="nested_method",
            type=EntityType.METHOD,
            byte_range=ByteRange(40, 70),
            line_range=LineRange(4, 7),
        ),
        EntityInfo(
            name="outer_function",
            type=EntityType.FUNCTION,
            byte_range=ByteRange(170, 205),
            line_range=LineRange(17, 19),
        ),
    ]

    enriched = enrich_parent_links(entities)
    by_name = {entity.name: entity for entity in enriched}

    assert by_name["Inner"].parent == "Outer"
    assert by_name["nested_method"].parent == "Inner"
    assert by_name["outer_function"].parent == "Outer"
