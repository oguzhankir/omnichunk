from __future__ import annotations

import importlib

import pytest

from omnichunk.budget.optimizer import TokenBudgetOptimizer, _dp_select
from omnichunk.formats.docx_loader import load_docx_bytes
from omnichunk.formats.ipynb import load_ipynb
from omnichunk.formats.pdf import _looks_code_like
from omnichunk.graph.builder import build_chunk_graph
from omnichunk.graph.types import ChunkGraph
from omnichunk.types import ByteRange, Chunk, ChunkContext, EntityInfo, EntityType, LineRange


def _mk_chunk(text: str, index: int, entities: list[EntityInfo]) -> Chunk:
    start = sum(len(text.encode("utf-8")) for _ in range(index))
    end = start + len(text.encode("utf-8"))
    return Chunk(
        text=text,
        contextualized_text=text,
        byte_range=ByteRange(start=start, end=end),
        line_range=LineRange(start=index, end=index),
        index=index,
        total_chunks=1,
        context=ChunkContext(filepath="f.py", language="python", entities=entities),
        token_count=max(1, len(text.split())),
        char_count=len(text),
        nws_count=max(1, sum(1 for c in text if not c.isspace())),
    )


def test_docx_loader_requires_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    orig = importlib.import_module

    def _fake_import(name: str) -> object:
        if name.startswith("docx"):
            raise ImportError("missing docx")
        return orig(name)

    monkeypatch.setattr(importlib, "import_module", _fake_import)
    with pytest.raises(ImportError):
        load_docx_bytes(b"not-a-docx")


def test_ipynb_loader_reports_invalid_shapes() -> None:
    invalid = load_ipynb("{")
    assert invalid.text == ""
    assert invalid.warnings and "invalid_json" in invalid.warnings[0]

    bad_cells = load_ipynb('{"cells": "nope"}')
    assert bad_cells.text == ""
    assert "missing_or_invalid_cells" in bad_cells.warnings


def test_pdf_code_like_detection_branches() -> None:
    assert _looks_code_like("def f(x): return x")
    assert _looks_code_like("a();\nb();\n{ x(); }\n{ y(); }")
    assert not _looks_code_like("")
    assert not _looks_code_like("just one sentence")


def test_graph_builder_ignores_import_entities() -> None:
    c0 = _mk_chunk(
        "import os",
        0,
        [EntityInfo(name="os", type=EntityType.IMPORT, is_partial=False)],
    )
    c1 = _mk_chunk(
        "def f(): pass",
        1,
        [EntityInfo(name="f", type=EntityType.FUNCTION, is_partial=False)],
    )
    graph = build_chunk_graph([c0, c1], min_entity_occurrences=1)
    assert "os" not in graph.nodes
    assert graph.entity_chunks("missing") == []


def test_chunk_graph_from_dict_defaults_and_neighbors() -> None:
    restored = ChunkGraph.from_dict({"nodes": {"x": {}}, "edges": [{"chunk_a": 2, "chunk_b": 1}]})
    assert restored.nodes["x"].entity_type == ""
    assert restored.chunk_count == 0
    assert restored.chunk_neighbors(1) == [2]


def test_budget_overlap_threshold_validation() -> None:
    with pytest.raises(ValueError):
        TokenBudgetOptimizer(budget=10, overlap_threshold=0)
    with pytest.raises(ValueError):
        TokenBudgetOptimizer(budget=10, overlap_threshold=1.5)


def test_dp_falls_back_to_greedy_for_large_state_space() -> None:
    chunks = [
        _mk_chunk("a b c d", 0, []),
        _mk_chunk("e f g h", 1, []),
        _mk_chunk("i j k l", 2, []),
    ]
    picked = _dp_select(chunks, [0.1, 0.2, 0.3], budget=20_000_000, size_unit="chars")
    assert picked
