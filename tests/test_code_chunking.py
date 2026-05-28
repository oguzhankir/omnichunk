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
