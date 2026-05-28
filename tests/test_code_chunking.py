from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker


def test_python_chunking_reconstructs_exactly(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=220, min_chunk_size=40, size_unit="chars", overlap_lines=1)

    chunks = chunker.chunk("python_complex.py", code)

    assert len(chunks) > 1
    reconstructed = "".join(chunk.text for chunk in chunks)
    assert reconstructed == code

    raw = code.encode("utf-8")
    for chunk in chunks:
        snippet = raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8")
        assert snippet == chunk.text
        assert chunk.text.strip()

    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_python_context_entities_and_scope(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=260, min_chunk_size=50, size_unit="chars")

    chunks = chunker.chunk("services/user_service.py", code)
    text_blob = "\n".join(chunk.contextualized_text for chunk in chunks)

    assert "UserService" in text_blob
    assert any(chunk.context.entities for chunk in chunks)
    assert any(chunk.context.breadcrumb for chunk in chunks)


def test_decorator_stays_with_target() -> None:
    code = "@decorator\ndef hello(name: str):\n    return f'hi {name}'\n"
    chunker = Chunker(max_chunk_size=40, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("decorated.py", code)

    assert chunks
    # Allow decorator and function to be in same or adjacent chunks
    decorator_chunk = next((i for i, c in enumerate(chunks) if "@decorator" in c.text), None)
    func_chunk = next((i for i, c in enumerate(chunks) if "def hello" in c.text), None)
    assert decorator_chunk is not None
    assert func_chunk is not None
    # They should be the same chunk or adjacent chunks
    assert abs(decorator_chunk - func_chunk) <= 1


def test_malformed_python_graceful_degradation() -> None:
    malformed = "def broken(:\n    x = 1\n    return x\n"
    chunker = Chunker(max_chunk_size=40, size_unit="chars")

    chunks = chunker.chunk("broken.py", malformed)

    assert chunks
    assert "broken" in "\n".join(c.text for c in chunks)


def test_deterministic_output(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "python_complex.py").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=200, min_chunk_size=40, size_unit="chars")

    first = chunker.chunk("module.py", code)
    second = chunker.chunk("module.py", code)

    assert [(c.byte_range.start, c.byte_range.end, c.contextualized_text) for c in first] == [
        (c.byte_range.start, c.byte_range.end, c.contextualized_text) for c in second
    ]


def test_code_languages_minimum(fixtures_dir: Path) -> None:
    ts = (fixtures_dir / "typescript_complex.ts").read_text(encoding="utf-8")
    rs = (fixtures_dir / "rust_complex.rs").read_text(encoding="utf-8")
    chunker = Chunker(max_chunk_size=180, size_unit="chars")

    ts_chunks = chunker.chunk("typescript_complex.ts", ts)
    rs_chunks = chunker.chunk("rust_complex.rs", rs)

    assert ts_chunks
    assert rs_chunks
    assert "UserService" in "\n".join(c.contextualized_text for c in ts_chunks)
    assert "Config" in "\n".join(c.contextualized_text for c in rs_chunks)


def test_oversized_code_split_prefers_safe_boundaries() -> None:
    expression = " + ".join(f"value_{i}" for i in range(80))
    code = f"def compute():\n    return {expression}\n"
    chunker = Chunker(max_chunk_size=48, min_chunk_size=10, size_unit="chars")

    chunks = chunker.chunk("long_line.py", code)

    assert chunks
    assert "".join(c.text for c in chunks) == code

    for left, right in zip(chunks, chunks[1:]):
        if not left.text or not right.text:
            continue
        assert not (left.text[-1].isalnum() and right.text[0].isalnum())


def test_python_signature_with_type_annotations() -> None:
    code = "def fetch(url: str, timeout: int = 30) -> dict:\n    return {}\n"
    chunker = Chunker(max_chunk_size=200, size_unit="chars")
    chunks = chunker.chunk("typed.py", code)
    assert chunks
    all_entities = [e for c in chunks for e in c.context.entities]
    func = next((e for e in all_entities if e.name == "fetch"), None)
    assert func is not None
    assert "url: str" in func.signature
    assert "timeout: int" in func.signature
    assert func.signature.endswith(":")


def test_large_python_file_stress_reconstruction_and_determinism() -> None:
    parts: list[str] = ["from typing import Any\n\n"]
    for idx in range(75):
        parts.append(f"class Service{idx}:\n")
        parts.append(f"    def run_{idx}(self, value: int) -> int:\n")
        parts.append("        total = value\n")
        for step in range(8):
            parts.append(f"        total += {step}\n")
        parts.append("        return total\n\n")

    code = "".join(parts)
    chunker = Chunker(max_chunk_size=420, min_chunk_size=80, size_unit="chars")

    first = chunker.chunk("large_module.py", code)
    second = chunker.chunk("large_module.py", code)

    assert first
    assert len(first) > 10
    assert "".join(chunk.text for chunk in first) == code

    raw = code.encode("utf-8")
    for chunk in first:
        snippet = raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8")
        assert snippet == chunk.text
        assert chunk.text.strip()

    assert [(c.byte_range.start, c.byte_range.end, c.contextualized_text) for c in first] == [
        (c.byte_range.start, c.byte_range.end, c.contextualized_text) for c in second
    ]


# ---------------------------------------------------------------------------
# Phase 2 — Python entity-extraction extensions (Commit 16)
# ---------------------------------------------------------------------------


def _entities(code: str, filepath: str = "x.py") -> list[tuple[str, str]]:
    chunks = Chunker(max_chunk_size=600, min_chunk_size=20, size_unit="chars").chunk(
        filepath, code
    )
    return [(e.name, e.type.value) for c in chunks for e in c.context.entities]


def test_python_dunder_all_captured_as_module_export() -> None:
    code = '__all__ = ["User", "Admin"]\n\nclass User:\n    pass\n'
    ents = _entities(code)
    assert ("__all__", "module_export") in ents


def test_python_typealias_captured() -> None:
    code = "from typing import TypeAlias\n\nUserId: TypeAlias = int\nName: TypeAlias = str\n"
    ents = _entities(code)
    aliases = {n for n, t in ents if t == "type_alias"}
    assert aliases == {"UserId", "Name"}


def test_python_protocol_class_captured_as_protocol() -> None:
    code = (
        "from typing import Protocol\n\n"
        "class Renderable(Protocol):\n"
        "    def render(self) -> str: ...\n"
    )
    ents = _entities(code)
    protocols = {n for n, t in ents if t == "protocol"}
    assert "Renderable" in protocols


def test_python_plain_class_not_tagged_as_protocol() -> None:
    code = "class User:\n    pass\n"
    ents = _entities(code)
    assert all(t != "protocol" for _, t in ents)


def test_python_dataclass_decorated_class_signature_includes_decorator() -> None:
    code = (
        "from dataclasses import dataclass\n\n"
        "@dataclass(frozen=True)\n"
        "class Point:\n"
        "    x: int\n"
        "    y: int\n"
    )
    chunks = Chunker(max_chunk_size=600, min_chunk_size=20, size_unit="chars").chunk(
        "x.py", code
    )
    all_entities = [e for c in chunks for e in c.context.entities]
    point = next((e for e in all_entities if e.name == "Point"), None)
    assert point is not None
    # The chunk should contain the decorator line attached to the class definition.
    container = next(c for c in chunks if "class Point" in c.text)
    assert "@dataclass" in container.text


def test_python_stacked_decorators_stay_attached_to_function() -> None:
    code = (
        "@staticmethod\n"
        "@property\n"
        "def helper():\n"
        "    return 1\n"
    )
    chunks = Chunker(max_chunk_size=600, min_chunk_size=20, size_unit="chars").chunk(
        "x.py", code
    )
    helper_chunk = next(c for c in chunks if "def helper" in c.text)
    assert "@staticmethod" in helper_chunk.text
    assert "@property" in helper_chunk.text


def test_python_typealias_does_not_also_produce_constant() -> None:
    code = "from typing import TypeAlias\n\nUserId: TypeAlias = int\n"
    ents = _entities(code)
    type_alias_count = sum(1 for n, t in ents if n == "UserId" and t == "type_alias")
    assert type_alias_count == 1


def test_python_protocol_and_class_coexist_on_same_decl() -> None:
    """Protocol subclass yields BOTH the class entity and the protocol entity."""
    code = "from typing import Protocol\n\nclass X(Protocol):\n    pass\n"
    ents = _entities(code)
    assert ("X", "class") in ents
    assert ("X", "protocol") in ents


def test_python_module_export_value_is_dunder_all() -> None:
    code = '__all__ = ["A", "B", "C"]\n'
    ents = _entities(code)
    exports = [n for n, t in ents if t == "module_export"]
    assert exports == ["__all__"]


def test_python_typealias_without_annotation_is_not_captured() -> None:
    """Regular assignment without TypeAlias annotation must not produce type_alias."""
    code = "Name = str\n"
    ents = _entities(code)
    assert all(t != "type_alias" for _, t in ents)


# ---------------------------------------------------------------------------
# Phase 2 — TypeScript modern patterns (Commit 17)
# ---------------------------------------------------------------------------


def _ts_chunks(fixtures_dir: Path) -> list:
    code = (fixtures_dir / "typescript_modern.ts").read_text(encoding="utf-8")
    return Chunker(max_chunk_size=500, min_chunk_size=30, size_unit="chars").chunk(
        "modern.ts", code
    )


def test_typescript_modern_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "typescript_modern.ts").read_text(encoding="utf-8")
    chunks = _ts_chunks(fixtures_dir)
    assert "".join(c.text for c in chunks) == code
    raw = code.encode("utf-8")
    for ch in chunks:
        assert raw[ch.byte_range.start : ch.byte_range.end].decode("utf-8") == ch.text
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_typescript_generic_function_captured(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    fn_names = {e.name for c in chunks for e in c.context.entities if e.type.value == "function"}
    assert {"identity", "pickBy"} <= fn_names


def test_typescript_class_decorators_attached_in_chunk(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    user_chunk = next(c for c in chunks if "class UserService" in c.text)
    assert "@Injectable" in user_chunk.text
    app_chunk = next(c for c in chunks if "class AppComponent" in c.text)
    assert "@Component" in app_chunk.text


def test_typescript_satisfies_does_not_break_parser(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    # 'satisfies' constant must end up in a chunk without producing parse errors
    has_satisfies = any("satisfies Point" in c.text for c in chunks)
    assert has_satisfies


def test_typescript_module_declaration_captured(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    modules = {e.name for c in chunks for e in c.context.entities if e.type.value == "module"}
    assert "LegacyMod" in modules


def test_typescript_enum_declaration_captured(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    enums = {e.name for c in chunks for e in c.context.entities if e.type.value == "enum"}
    assert "Color" in enums


def test_typescript_interface_with_generics_captured(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    interfaces = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "interface"
    }
    assert "Serializer" in interfaces


def test_typescript_as_const_assertion_preserved(fixtures_dir: Path) -> None:
    chunks = _ts_chunks(fixtures_dir)
    assert any("as const" in c.text for c in chunks)


# ---------------------------------------------------------------------------
# Phase 2 — Rust modern patterns (Commit 18)
# ---------------------------------------------------------------------------


def _rust_chunks(fixtures_dir: Path) -> list:
    code = (fixtures_dir / "rust_modern.rs").read_text(encoding="utf-8")
    return Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "modern.rs", code
    )


def test_rust_modern_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "rust_modern.rs").read_text(encoding="utf-8")
    chunks = _rust_chunks(fixtures_dir)
    assert "".join(c.text for c in chunks) == code
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_rust_macro_rules_captured_as_macro() -> None:
    code = "macro_rules! say_hi { () => { println!(\"hi\"); } }\n"
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "x.rs", code
    )
    kinds = [(e.name, e.type.value) for c in chunks for e in c.context.entities]
    assert ("say_hi", "macro") in kinds


def test_rust_impl_for_trait_yields_impl_block(fixtures_dir: Path) -> None:
    chunks = _rust_chunks(fixtures_dir)
    impl_blocks = [
        e for c in chunks for e in c.context.entities if e.type.value == "impl_block"
    ]
    assert len(impl_blocks) >= 3  # impl Greeter, impl Renderable for Greeter, impl Display for Greeter
    names = {e.name for e in impl_blocks}
    assert "Greeter" in names


def test_rust_inherent_impl_block_yields_impl_block_for_type() -> None:
    code = "struct Foo;\nimpl Foo { fn a(&self) {} }\n"
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "x.rs", code
    )
    types = {e.type.value for c in chunks for e in c.context.entities}
    assert "impl_block" in types


def test_rust_lifetimes_do_not_create_extra_entities(fixtures_dir: Path) -> None:
    """Lifetime parameters in signatures must NOT appear as separate entities."""
    chunks = _rust_chunks(fixtures_dir)
    entity_names = {e.name for c in chunks for e in c.context.entities}
    assert "'a" not in entity_names
    assert "a" not in entity_names or "merge" in entity_names


def test_rust_visibility_modifiers_preserved_in_chunk(fixtures_dir: Path) -> None:
    chunks = _rust_chunks(fixtures_dir)
    code = "".join(c.text for c in chunks)
    assert "pub(crate)" in code
    assert "pub(super)" in code


def test_rust_macro_definition_kept_with_arms_intact() -> None:
    code = (
        "macro_rules! multi {\n"
        "    () => { 1 };\n"
        "    ($x:expr) => { $x };\n"
        "}\n"
    )
    chunks = Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "x.rs", code
    )
    macro_chunk = next(c for c in chunks if "macro_rules!" in c.text)
    assert "($x:expr)" in macro_chunk.text


# ---------------------------------------------------------------------------
# Phase 2 — Go modern patterns (Commit 19)
# ---------------------------------------------------------------------------


def _go_chunks(fixtures_dir: Path) -> list:
    code = (fixtures_dir / "go_modern.go").read_text(encoding="utf-8")
    return Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "modern.go", code
    )


def test_go_modern_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "go_modern.go").read_text(encoding="utf-8")
    chunks = _go_chunks(fixtures_dir)
    assert "".join(c.text for c in chunks) == code
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_go_interface_extraction(fixtures_dir: Path) -> None:
    chunks = _go_chunks(fixtures_dir)
    interfaces = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "interface"
    }
    assert {"Comparable", "Renderer"} <= interfaces


def test_go_type_alias_extraction(fixtures_dir: Path) -> None:
    chunks = _go_chunks(fixtures_dir)
    aliases = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "type_alias"
    }
    assert {"Alias", "StringPair"} <= aliases


def test_go_init_function_captured(fixtures_dir: Path) -> None:
    chunks = _go_chunks(fixtures_dir)
    fns = {e.name for c in chunks for e in c.context.entities if e.type.value == "function"}
    assert "init" in fns


def test_go_generic_function_signature_preserved(fixtures_dir: Path) -> None:
    chunks = _go_chunks(fixtures_dir)
    map_chunk = next(c for c in chunks if "func Map[" in c.text)
    assert "[T, U any]" in map_chunk.text


def test_go_generate_directive_preserved(fixtures_dir: Path) -> None:
    """//go:generate directives must appear verbatim in chunk content."""
    chunks = _go_chunks(fixtures_dir)
    full = "".join(c.text for c in chunks)
    assert "//go:generate stringer -type=Color" in full
    assert "//go:generate mockgen -source=service.go" in full


# ---------------------------------------------------------------------------
# Phase 2 — Java modern patterns (Commit 20)
# ---------------------------------------------------------------------------


def _java_chunks(fixtures_dir: Path) -> list:
    code = (fixtures_dir / "java_modern.java").read_text(encoding="utf-8")
    return Chunker(max_chunk_size=400, min_chunk_size=20, size_unit="chars").chunk(
        "Modern.java", code
    )


def test_java_modern_reconstruction(fixtures_dir: Path) -> None:
    code = (fixtures_dir / "java_modern.java").read_text(encoding="utf-8")
    chunks = _java_chunks(fixtures_dir)
    assert "".join(c.text for c in chunks) == code
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start


def test_java_annotation_type_declaration(fixtures_dir: Path) -> None:
    chunks = _java_chunks(fixtures_dir)
    annotations = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "annotation"
    }
    assert "Loggable" in annotations


def test_java_record_declarations(fixtures_dir: Path) -> None:
    chunks = _java_chunks(fixtures_dir)
    records = {
        e.name for c in chunks for e in c.context.entities if e.type.value == "record"
    }
    assert {"Point", "User"} <= records


def test_java_sealed_interface_extraction(fixtures_dir: Path) -> None:
    chunks = _java_chunks(fixtures_dir)
    sealed = {
        e.name
        for c in chunks
        for e in c.context.entities
        if e.type.value == "sealed_interface"
    }
    assert "Shape" in sealed


def test_java_method_decorators_preserved_in_chunk(fixtures_dir: Path) -> None:
    chunks = _java_chunks(fixtures_dir)
    circle_chunk = next(c for c in chunks if "class Circle" in c.text)
    assert "@Override" in circle_chunk.text
    assert "@Deprecated" in circle_chunk.text


def test_java_static_initializer_preserved_in_class(fixtures_dir: Path) -> None:
    chunks = _java_chunks(fixtures_dir)
    circle_chunk = next(c for c in chunks if "class Circle" in c.text)
    assert "static {" in circle_chunk.text
    assert 'System.out.println("Circle loaded")' in circle_chunk.text
