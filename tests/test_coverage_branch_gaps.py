from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from omnichunk import ChunkOptions, dedup_chunks, evaluate_chunks
from omnichunk.budget.optimizer import _jaccard_nws
from omnichunk.context.entities import (
    _child_by_field_name,
    _dedupe_entities,
    _expand_rust_use_paths,
    _fallback_regex_entities,
    _find_block_end,
    _find_matching_brace,
    _join_rust_path,
    _line_for_char_offset,
    _normalize_name,
    _parse_go_imports,
    _parse_java_imports,
    _parse_python_imports,
    _parse_rust_imports,
    _parse_ts_js_imports,
    _split_top_level_csv,
    enrich_parent_links,
)
from omnichunk.engine.semantic_engine import SemanticEngine
from omnichunk.eval import eval_report_to_dict
from omnichunk.formats.chunk import chunk_loaded_document
from omnichunk.formats.ipynb import load_ipynb
from omnichunk.formats.types import FormatSegment, LoadedDocument
from omnichunk.graph.builder import build_chunk_graph
from omnichunk.serialization import (
    chunk_from_dict,
    chunk_to_dict,
    chunks_to_jsonl,
    chunks_to_langchain_docs,
    chunks_to_llamaindex_docs,
)
from omnichunk.sizing.nws import preprocess_nws_cumsum
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ContentType,
    EntityInfo,
    EntityType,
    LineRange,
)
from omnichunk.util.detect import (
    _looks_hybrid_python,
    _looks_like_code,
    _looks_like_markup,
    detect_content_type,
    detect_language,
)
from omnichunk.windowing.models import ASTNodeWindowItem
from omnichunk.windowing.split import find_statement_boundary, split_oversized_leaf


def test_normalize_name_strips_and_truncates_call() -> None:
    assert _normalize_name("  Foo(`x`)  ") == "Foo"
    assert _normalize_name("bar") == "bar"


def test_parse_python_imports_variants() -> None:
    assert ("os", "os") in _parse_python_imports("import os, sys as s")
    pairs = _parse_python_imports("from pkg.mod import a as b, c")
    assert ("b", "pkg.mod") in pairs
    assert ("c", "pkg.mod") in pairs
    star = _parse_python_imports("from pkg.sub import *")
    assert star == [("pkg.sub", "pkg.sub")]


def test_parse_ts_js_imports_variants() -> None:
    assert _parse_ts_js_imports("import * as ns from 'x/y'") == [("ns", "x/y")]
    multi = _parse_ts_js_imports('import Foo, { Bar as Baz } from "pkg/mod"')
    names = [n for n, _ in multi]
    assert "Foo" in names and "Baz" in names


def test_parse_rust_use_brace_group_and_alias() -> None:
    out = _parse_rust_imports("use foo::{Bar, baz::Q as R};")
    names = {x[0] for x in out}
    assert "Bar" in names or "R" in names


def test_parse_rust_self_leaf_rewrites() -> None:
    out = _parse_rust_imports("use crate::modname::self;")
    assert out


def test_expand_rust_invalid_brace_falls_back() -> None:
    assert _expand_rust_use_paths("foo{unclosed") == ["foo{unclosed"]


def test_find_matching_brace_and_split_csv() -> None:
    assert _find_matching_brace("a{b{c}d}e", 1) == 7
    assert _split_top_level_csv("a, b{c,d},e") == ["a", " b{c,d}", "e"]


def test_join_rust_path() -> None:
    assert _join_rust_path("", "foo") == "foo"
    assert _join_rust_path("a", "") == "a"
    assert _join_rust_path("a::", "b") == "a::b"


def test_parse_go_import_block_and_alias() -> None:
    block = 'import (\n  f "fmt"\n  _ "embed"\n)\n'
    got = _parse_go_imports(block)
    assert ("f", "fmt") in got
    assert any(name == "embed" for name, _ in got)

    single = 'import `example.com/foo/bar`'
    got2 = _parse_go_imports(single)
    assert got2 and got2[0][0]


def test_parse_java_imports_star_and_class() -> None:
    j = "import java.util.List;\nimport static pkg.Outer.*;\n"
    got = _parse_java_imports(j)
    assert any(name == "List" for name, _ in got)
    assert any(name == "Outer" for name, src in got if "pkg" in src)


def test_child_by_field_name_errors_return_none() -> None:
    class N:
        def child_by_field_name(self, _n: str) -> None:
            raise RuntimeError("nope")

    assert _child_by_field_name(N(), "x") is None
    assert _child_by_field_name(object(), "x") is None


def test_fallback_regex_entities_python() -> None:
    code = (
        "from x import y as z\n"
        "import a.b as c\n"
        "async def outer():\n"
        "    pass\n"
        "def inner():\n"
        "    return 1\n"
        "class Cls:\n"
        "    pass\n"
    )
    ent = _fallback_regex_entities(code, "python")
    names = {e.name for e in ent}
    assert "z" in names and "inner" in names and "Cls" in names


def test_fallback_regex_entities_non_python_empty() -> None:
    assert _fallback_regex_entities("def f(): pass", "rust") == []


def test_find_block_end_and_line_for_offset() -> None:
    one = "def f(): return 1"
    end = _find_block_end(one, 0)
    assert end >= len(one)

    nested = "def outer():\n    def inner():\n        return 1\n    return inner\nx = 1\n"
    end2 = _find_block_end(nested, nested.index("def outer"))
    assert "return inner" in nested[:end2]

    nls = [i for i, ch in enumerate(nested) if ch == "\n"]
    assert _line_for_char_offset(nls, 0) == 0
    assert _line_for_char_offset(nls, 10**9) == len(nls)


def test_dedupe_entities_and_enrich_parent_links() -> None:
    br = ByteRange(0, 100)
    outer = EntityInfo(
        name="Outer",
        type=EntityType.CLASS,
        byte_range=br,
        line_range=LineRange(0, 1),
    )
    inner = EntityInfo(
        name="inner",
        type=EntityType.FUNCTION,
        byte_range=ByteRange(10, 50),
        line_range=LineRange(1, 2),
    )
    dup_pair = [
        EntityInfo("x", EntityType.FUNCTION, byte_range=ByteRange(2, 4)),
        EntityInfo("x", EntityType.FUNCTION, byte_range=ByteRange(2, 4)),
    ]
    assert len(_dedupe_entities(dup_pair)) == 1

    enriched = enrich_parent_links([inner, outer])
    by_name = {e.name: e for e in enriched}
    assert by_name["inner"].parent == "Outer"


def test_jaccard_nws_edge_cases() -> None:
    assert _jaccard_nws("", "") == 1.0
    assert _jaccard_nws("a", "") == 0.0


def test_find_statement_boundary_escape_in_string() -> None:
    src = b'x = "\\\\\\n"\n'
    assert find_statement_boundary(src, 0, len(src), len(src)) == len(src)


def test_split_oversized_leaf_degenerate_and_hard_split() -> None:
    code = "abcd"
    cum = preprocess_nws_cumsum(code, backend="python")
    b = code.encode("utf-8")

    dead = ASTNodeWindowItem(node=None, start=10, end=5, size=1)
    assert list(split_oversized_leaf(dead, code=code, cumsum=cum, max_size=1)) == []

    empty_seg = ASTNodeWindowItem(node=None, start=0, end=0, size=1)
    assert list(split_oversized_leaf(empty_seg, code=code, cumsum=cum, max_size=1)) == []

    whole = ASTNodeWindowItem(node=None, start=0, end=len(b), size=10**6)
    parts = list(split_oversized_leaf(whole, code=code, cumsum=cum, max_size=1))
    assert len(parts) >= 1


def test_eval_metrics_branches_and_report_dict() -> None:
    raw = "alpha beta. gamma delta."
    chunker_context = ChunkContext(
        filepath="t.txt", language="plaintext", content_type=ContentType.PROSE
    )
    chunks = []
    off = 0
    for i, piece in enumerate(["alpha beta. ", "gamma delta."]):
        b = piece.encode("utf-8")
        chunks.append(
            Chunk(
                text=piece,
                contextualized_text=piece,
                byte_range=ByteRange(off, off + len(b)),
                line_range=LineRange(i, i),
                index=i,
                total_chunks=2,
                context=chunker_context,
                token_count=3,
                char_count=len(piece),
                nws_count=sum(1 for c in piece if not c.isspace()),
            )
        )
        off += len(b)

    r_all = evaluate_chunks(chunks, source=raw, metrics="all")
    assert r_all.aggregate.get("reconstruction") == 1.0
    r_sub = evaluate_chunks(chunks, source=raw, metrics=("density", "boundary_quality"))
    assert r_sub.aggregate.get("coherence") is None
    d = eval_report_to_dict(r_sub)
    assert "aggregate" in d and len(d["per_chunk"]) == 2

    bad = Chunk(
        text="x",
        contextualized_text="x",
        byte_range=ByteRange(100, 200),
        line_range=LineRange(0, 0),
        index=0,
        total_chunks=1,
        context=chunker_context,
        token_count=1,
        char_count=1,
        nws_count=1,
    )
    br = evaluate_chunks([bad], source="ab", metrics=("reconstruction",))
    assert br.per_chunk[0].reconstruction == 0.0

    cov = evaluate_chunks(
        [replace(bad, byte_range=ByteRange(0, 1), text="")],
        source="ab",
        metrics=("coverage",),
    )
    assert cov.per_chunk[0].coverage == 1.0


def test_dedup_simhash_finds_duplicate() -> None:
    text = "the quick brown fox jumps " * 15 + "extra"
    raw = text.encode("utf-8")
    nws = sum(1 for c in text if not c.isspace())
    ctx = ChunkContext(filepath="a.py", language="python")
    chunks = []
    for i in range(8):
        chunks.append(
            Chunk(
                text=text,
                contextualized_text=text,
                byte_range=ByteRange(0, len(raw)),
                line_range=LineRange(0, 1),
                index=i,
                total_chunks=8,
                context=ctx,
                char_count=len(text),
                nws_count=nws,
            )
        )
    kept, dup_map = dedup_chunks(chunks, method="simhash", threshold=0.98)
    assert len(kept) < len(chunks)
    assert dup_map


def test_chunk_from_dict_content_type_branches() -> None:
    d = {
        "text": "hi",
        "contextualized_text": "hi",
        "byte_range": {"start": 0, "end": 2},
        "line_range": {"start": 0, "end": 0},
        "index": 0,
        "total_chunks": 1,
        "context": {"filepath": "f", "language": "plaintext", "content_type": 123},
        "token_count": 1,
        "char_count": 2,
        "nws_count": 2,
    }
    ch = chunk_from_dict(d)
    assert ch.context.content_type == ContentType.PROSE

    d2 = dict(d)
    d2["context"] = {"content_type": "not-a-real-type"}
    ch2 = chunk_from_dict(d2)
    assert ch2.context.content_type == ContentType.PROSE


def test_chunks_to_jsonl_writes_file(tmp_path: Path) -> None:
    ctx = ChunkContext(filepath="a.py", language="python")
    ch = Chunk(
        text="x",
        contextualized_text="x",
        byte_range=ByteRange(0, 1),
        line_range=LineRange(0, 0),
        index=0,
        total_chunks=1,
        context=ctx,
        token_count=1,
        char_count=1,
        nws_count=1,
    )
    out = tmp_path / "out.jsonl"
    chunks_to_jsonl([ch], output_path=str(out))
    assert out.read_text(encoding="utf-8").strip()


def test_chunk_to_dict_round_trip_minimal() -> None:
    ctx = ChunkContext(filepath="a.py", language="python")
    ch = Chunk(
        text="x",
        contextualized_text="x",
        byte_range=ByteRange(0, 1),
        line_range=LineRange(0, 0),
        index=0,
        total_chunks=1,
        context=ctx,
        token_count=1,
        char_count=1,
        nws_count=1,
    )
    d = chunk_to_dict(ch)
    ch2 = chunk_from_dict(d)
    assert ch2.text == ch.text


def test_load_ipynb_invalid_json_and_cells() -> None:
    payload = json.dumps(
        {
            "cells": [
                {"cell_type": "markdown", "source": ["# H\n"]},
                {"cell_type": "code", "source": "print(1)"},
            ]
        }
    )
    loaded = load_ipynb(payload)
    assert "# H" in loaded.text

    bad = load_ipynb("{")
    assert bad.text == ""
    assert bad.warnings and "invalid_json" in bad.warnings[0]

    empty_cells = load_ipynb('{"cells": null}')
    assert empty_cells.warnings == ("missing_or_invalid_cells",)


def test_load_ipynb_raw_outputs_and_unknown_cell() -> None:
    payload = {
        "cells": [
            {"cell_type": "raw", "source": ["rawline\n"]},
            {"cell_type": "mystery", "source": "x"},
            {
                "cell_type": "code",
                "metadata": {"language": "rust"},
                "source": ["1+1"],
                "outputs": [
                    {"output_type": "stream", "text": ["stdout"]},
                    {"output_type": "stream", "text": 99},
                    {"output_type": "execute_result", "data": {"text/plain": "42"}},
                    {"output_type": "display_data", "data": {"text/plain": ["z"]}},
                    {"output_type": "error", "traceback": ["e1", "e2"]},
                    "skip",
                    {"output_type": "execute_result", "data": {}},
                ],
            },
        ]
    }
    loaded = load_ipynb(json.dumps(payload), include_outputs=True)
    assert "rawline" in loaded.text
    assert "[output]" in loaded.text
    assert any(w.startswith("unknown_cell_type") for w in loaded.warnings)
    rust_seg = [s for s in loaded.segments if s.kind == "code"]
    assert rust_seg and rust_seg[0].metadata.get("language") == "rust"


def test_chunk_loaded_document_merges_segments() -> None:
    seg_a = FormatSegment(char_start=0, char_end=4, kind="prose", metadata={})
    seg_b = FormatSegment(
        char_start=4, char_end=8, kind="code", metadata={"language": "python"}
    )
    doc = LoadedDocument(
        text="aaaaBBBB",
        segments=(seg_a, seg_b),
        format_name="testfmt",
        warnings=(),
    )
    chunks = chunk_loaded_document("f.fake", doc, ChunkOptions())
    assert len(chunks) >= 1


def test_build_chunk_graph_partial_flags_and_edges() -> None:
    c0 = Chunk(
        text="class A: pass",
        contextualized_text="class A: pass",
        byte_range=ByteRange(0, 20),
        line_range=LineRange(0, 0),
        index=0,
        total_chunks=2,
        context=ChunkContext(
            filepath="m.py",
            language="python",
            entities=(
                EntityInfo(name="A", type=EntityType.CLASS, is_partial=True),
                EntityInfo(name="shared", type=EntityType.FUNCTION, is_partial=False),
            ),
        ),
        token_count=3,
        char_count=13,
        nws_count=10,
    )
    c1 = Chunk(
        text="def shared(): pass",
        contextualized_text="def shared(): pass",
        byte_range=ByteRange(20, 40),
        line_range=LineRange(1, 1),
        index=1,
        total_chunks=2,
        context=ChunkContext(
            filepath="m.py",
            language="python",
            entities=(EntityInfo(name="shared", type=EntityType.FUNCTION, is_partial=False),),
        ),
        token_count=4,
        char_count=18,
        nws_count=14,
    )
    g = build_chunk_graph([c0, c1], min_entity_occurrences=2, ignore_types=frozenset())
    assert g.entity_chunks("shared")
    if g.edges:
        assert g.chunk_neighbors(0) or g.chunk_neighbors(1)


def test_detect_language_and_content_type_branches() -> None:
    assert detect_language("foo.d.ts") == "typescript"
    assert detect_language("", "# Title\n") == "markdown"
    assert detect_language("", "<!DOCTYPE html><html>") == "html"
    assert detect_language("", '{"a": 1}') == "json"
    assert detect_language("", "def f():\n  pass\n") == "python"
    assert detect_language("", "const x = 1\ninterface A {}\n") == "typescript"
    assert detect_language("", "package main\nfunc main() {}\n") == "go"
    assert detect_language("", "fn foo() {}\nimpl Bar {}\n") == "rust"
    assert detect_language("", "") == "plaintext"

    assert detect_content_type("x.ipynb", "", language="jupyter") == ContentType.HYBRID
    assert detect_content_type("file.mdx", "text") == ContentType.HYBRID
    assert detect_content_type("c.py", '# %%\nx=1\n') == ContentType.HYBRID
    ds = '"""' + ("x" * 50) + '"""\n' + "y" * 30
    assert detect_content_type("h.py", ds, language="python") == ContentType.HYBRID
    assert detect_content_type("j.json", "", language="json") == ContentType.MARKUP
    assert detect_content_type("", "<!DOCTYPE html><html></html>") == ContentType.MARKUP


def test_content_heuristic_helpers() -> None:
    assert not _looks_like_code("")
    assert _looks_like_code("def a():\n  pass\nreturn 1\n")
    assert not _looks_like_markup("")
    assert _looks_like_markup("<div>x</div>")
    assert not _looks_hybrid_python("")
    long_doc = '"""' + ("x" * 200) + '"""'
    assert _looks_hybrid_python(long_doc + "\n" + ("y" * 40))


def test_semantic_engine_chunk_stream_and_validation() -> None:
    rng = np.random.default_rng(3)

    def embed(texts: list[str]) -> np.ndarray:
        return rng.standard_normal((len(texts), 4))

    text = "First. Second. Third sentence here."
    opts = ChunkOptions(
        max_chunk_size=120,
        size_unit="chars",
        semantic_embed_fn=embed,
        semantic_window=2,
        semantic_threshold=0.5,
        _precomputed_nws_cumsum=preprocess_nws_cumsum(text),
    )
    eng = SemanticEngine()
    out = eng.chunk("s.md", text, opts)
    assert out
    streamed = list(eng.stream("s.md", text, opts))
    assert streamed and all(c.total_chunks == -1 for c in streamed)

    with pytest.raises(ValueError, match="semantic_embed_fn"):
        eng.chunk("s.md", text, replace(opts, semantic_embed_fn=None))


def test_langchain_export_shapes() -> None:
    pytest.importorskip("langchain_core.documents")
    ctx = ChunkContext(filepath="a.py", language="python")
    ch = Chunk(
        text="body",
        contextualized_text="ctx",
        byte_range=ByteRange(0, 4),
        line_range=LineRange(0, 0),
        index=0,
        total_chunks=1,
        context=ctx,
        token_count=1,
        char_count=4,
        nws_count=4,
    )
    lc = chunks_to_langchain_docs([ch])
    assert lc and hasattr(lc[0], "page_content")
    assert lc[0].page_content == "ctx"


def test_llamaindex_export_shapes() -> None:
    pytest.importorskip("llama_index.core.schema")
    ctx = ChunkContext(filepath="a.py", language="python")
    ch = Chunk(
        text="body",
        contextualized_text="ctx",
        byte_range=ByteRange(0, 4),
        line_range=LineRange(0, 0),
        index=0,
        total_chunks=1,
        context=ctx,
        token_count=1,
        char_count=4,
        nws_count=4,
    )
    li = chunks_to_llamaindex_docs([ch], use_contextualized_text=False)
    assert li and hasattr(li[0], "text")
    assert li[0].text == "body"
