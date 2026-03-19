from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker


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
