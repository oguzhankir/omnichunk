"""Offline conformance against the real, optional Docling schema and frameworks."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from omnichunk import (
    Chunker,
    ChunkingError,
    ChunkOptions,
    chunk_from_dict,
    chunk_loaded_document,
    load_docling_document,
)
from omnichunk.serialization import (
    chunks_to_jsonl,
    chunks_to_langchain_docs,
    chunks_to_llamaindex_docs,
    stable_chunk_id,
)

FIXTURE = Path(__file__).parent / "fixtures" / "docling_document.json"
OPTIONS = ChunkOptions(max_chunk_size=120, min_chunk_size=0, coverage_policy="lossless")


@pytest.fixture
def payload():
    pytest.importorskip("docling_core.types.doc")
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load(payload):
    return load_docling_document(payload, source_id="manual:17", extraction_revision="extract:v1")


def references(chunk):
    return chunk.context.format_metadata["elements"]


def assert_source(chunks, loaded, *, overlap=False):
    raw = loaded.text.encode("utf-8")
    covered = bytearray(len(raw))
    for chunk in chunks:
        span = chunk.byte_range
        assert raw[span.start : span.end].decode("utf-8") == chunk.text
        covered[span.start : span.end] = b"\1" * (span.end - span.start)
        assert chunk.source.revision == hashlib.sha256(raw).hexdigest()
        assert chunk.source.source_id == "manual:17"
        assert chunk.source.metadata["extraction_revision"] == "extract:v1"
        assert chunk.source.format_name == "docling"
        assert {r["element_id"] for r in references(chunk)} == {
            e.element_id
            for e in loaded.elements
            if e.byte_range.start < span.end and e.byte_range.end > span.start
        }
        for ref in references(chunk):
            assert ref["chunk_byte_range"] == {
                "start": max(span.start, ref["byte_range"]["start"]),
                "end": min(span.end, ref["byte_range"]["end"]),
            }
            assert ref["is_partial"] == (ref["chunk_byte_range"] != ref["byte_range"])
    assert all(covered)
    if not overlap:
        assert "".join(c.text for c in chunks) == loaded.text


def test_real_schema_native_and_exported_input_are_deterministic_and_immutable(payload):
    from docling_core.types.doc import DoclingDocument

    original = deepcopy(payload)
    native = DoclingDocument.model_validate(deepcopy(payload))
    assert native.version == "1.10.0"
    loaded = load(payload)
    assert load(native) == loaded
    assert payload == original
    chunks = chunk_loaded_document("guide.pdf", loaded, OPTIONS)
    assert chunks == chunk_loaded_document("guide.pdf", load(payload), OPTIONS)
    assert_source(chunks, loaded)
    assert loaded.metadata["origin"]["uri"] == "https://example.org/authored-fixture.pdf"
    assert any(
        e.kind == "list_item" and e.metadata["list"]["marker"] == "1." for e in loaded.elements
    )
    assert any(
        e.kind == "code" and e.metadata["code_language"] == "Python" for e in loaded.elements
    )
    for text in ["ıİ", "中文没有空格。", "e\u0301", "👩‍💻", 'return "你好 👩‍💻"']:
        assert text in loaded.text


def test_multiple_pages_and_elements_in_one_chunk_keep_original_geometry(payload):
    loaded = load(payload)
    chunks = chunk_loaded_document("guide.pdf", loaded, replace(OPTIONS, max_chunk_size=2000))
    first = chunks[0]
    assert [r["element_id"] for r in references(first)] == [f"#/texts/{i}" for i in range(4)]
    provenance = [p for r in references(first) for p in r["metadata"]["provenance"]]
    assert {p["page_no"] for p in provenance} == {1, 2}
    assert {p["bbox"]["coord_origin"] for p in provenance} == {"TOPLEFT", "BOTTOMLEFT"}
    for p in provenance:
        assert p["page_size"] == {"width": 600.0, "height": 800.0}
        assert p["coordinate_units"] is None
        original = next(
            r
            for r in payload["texts"]
            if r["prov"]
            and r["prov"][0]["page_no"] == p["page_no"]
            and list(r["prov"][0]["charspan"]) == p["docling_charspan"]
        )
        assert original["prov"][0]["bbox"] == p["bbox"]
    assert_source(chunks, loaded)


@pytest.mark.parametrize("unit", ["chars", "nws", "tokens"])
@pytest.mark.parametrize("context_mode", ["none", "full"])
def test_unicode_budgets_lossless_overlap_and_exact_element_intersections(
    payload, unit, context_mode
):
    loaded = load(payload)

    def counter(text):
        return len(text.encode("utf-8")) + 3

    options = replace(
        OPTIONS, size_unit=unit, tokenizer=counter, context_mode=context_mode, overlap=9
    )
    chunks = chunk_loaded_document("g.pdf", loaded, options)
    assert_source(chunks, loaded, overlap=True)
    size = {"chars": len, "nws": lambda t: sum(not ch.isspace() for ch in t), "tokens": counter}[
        unit
    ]
    for chunk in chunks:
        assert size(chunk.contextualized_text) <= options.max_chunk_size
        assert chunk.metadata["budget"]["size"] == size(chunk.contextualized_text)
        assert chunk.metadata["budget"]["rendered_token_count"] == counter(
            chunk.contextualized_text
        )
    assert any(len(references(c)) > 1 for c in chunks)
    assert any(c.byte_range.start < p.byte_range.end for p, c in zip(chunks, chunks[1:]))


def test_table_rows_headers_empty_cells_and_oversized_row_are_traceable(payload):
    loaded = load(payload)
    chunks = chunk_loaded_document("g.pdf", loaded, OPTIONS)
    table_chunks = [c for c in chunks if any(r["kind"] == "table" for r in references(c))]
    assert len(table_chunks) > 4
    derived = [c for c in table_chunks if "# Table headers (derived)" in c.contextualized_text]
    assert derived
    for chunk in derived:
        ctx = chunk.context.format_metadata["table_context"]
        assert ctx["text"] == "Ad\tDeğer\tNot\n"
        assert "Ad\tDeğer\tNot\n" not in chunk.text
        assert ctx["headers"][0]["element_id"] == "#/tables/0"
        assert ctx["headers"][0]["row_index"] == 0
        assert chunk.metadata["budget"]["size"] == len(chunk.contextualized_text) <= 120
    table = next(e.metadata["table"] for e in loaded.elements if e.kind == "table")
    empty = table["rows"][1]["cells"][2]
    assert empty["byte_range"]["start"] == empty["byte_range"]["end"]
    assert empty["header_cell_refs"] == [
        "#/tables/0/data/table_cells/2",
        "#/tables/0/data/table_cells/3",
    ]
    assert empty["page_no"] is None  # Docling cell boxes do not carry a page ID.
    assert empty["bbox"]["coord_origin"] == "TOPLEFT"
    assert table["rows"][3]["cells"][1]["bbox"] is None
    for row in table["rows"]:
        matches = [
            r
            for c in table_chunks
            for e in references(c)
            for r in e["metadata"].get("table", {}).get("rows", [])
            if r["row_index"] == row["row_index"]
        ]
        if row["row_index"] == 3:
            assert len(matches) > 1 and all(r["is_partial"] for r in matches)
        else:
            assert len(matches) == 1 and not matches[0]["is_partial"]
    assert_source(chunks, loaded)


@pytest.mark.parametrize("policy", ["error", "preserve"])
def test_oversized_row_uses_existing_overflow_contract(payload, policy):
    loaded = load(payload)
    options = replace(OPTIONS, overflow_policy=policy)
    if policy == "error":
        with pytest.raises(ChunkingError, match="exceeds"):
            chunk_loaded_document("g.pdf", loaded, options)
    else:
        chunks = chunk_loaded_document("g.pdf", loaded, options)
        assert_source(chunks, loaded)
        overflowing = [c for c in chunks if c.metadata["budget"]["overflow"]]
        assert overflowing
        assert all(
            c.metadata["overflow_reason"] == "structure-preserving policy" for c in overflowing
        )
        assert any(c.text.count("çok uzun") == 35 and "tail" in c.text for c in overflowing)


def test_context_overflow_keeps_metadata_or_raises_and_none_renders_raw(payload):
    loaded = load(payload)
    options = replace(OPTIONS, max_chunk_size=22)
    chunks = chunk_loaded_document("very/long/guide.pdf", loaded, options)
    assert any(c.metadata.get("context_omitted") for c in chunks)
    assert all(c.contextualized_text == c.text for c in chunks if c.metadata.get("context_omitted"))
    assert all(references(c) for c in chunks)
    with pytest.raises(ChunkingError, match="Context exceeds payload budget"):
        chunk_loaded_document(
            "very/long/guide.pdf", loaded, replace(options, context_overflow="error")
        )
    assert all(
        c.contextualized_text == c.text
        for c in chunk_loaded_document("guide.pdf", loaded, replace(OPTIONS, context_mode="none"))
    )


@pytest.mark.parametrize("framework", ["langchain", "llamaindex"])
@pytest.mark.parametrize("contextualized", [False, True])
def test_json_and_real_framework_roundtrips_preserve_every_reference(
    payload, framework, contextualized
):
    loaded = load(payload)
    chunks = chunk_loaded_document("g.pdf", loaded, OPTIONS)
    restored = [chunk_from_dict(json.loads(line)) for line in chunks_to_jsonl(chunks).splitlines()]
    assert restored == chunks
    if framework == "langchain":
        pytest.importorskip("langchain_core")
        from langchain_core.documents import Document

        from omnichunk.integrations.langchain import OmniChunkTextSplitter

        docs = chunks_to_langchain_docs(restored, use_contextualized_text=contextualized)
        docs = [
            Document(
                **json.loads(
                    doc.model_dump_json() if hasattr(doc, "model_dump_json") else doc.json()
                )
            )
            for doc in docs
        ]
        with pytest.raises(ValueError, match="already be chunked"):
            OmniChunkTextSplitter().split_documents(docs)
        contents = [doc.page_content for doc in docs]
        ids = [doc.id for doc in docs]
    else:
        pytest.importorskip("llama_index.core")
        from llama_index.core.schema import Document, MetadataMode

        from omnichunk.integrations.llamaindex import OmniChunkNodeParser

        docs = Chunker().to_llamaindex_docs(
            restored, use_contextualized_text=contextualized, include_metadata_in_content=False
        )
        docs = [Document.from_dict(json.loads(doc.to_json())) for doc in docs]
        with pytest.raises(ValueError, match="already be chunked"):
            OmniChunkNodeParser()(docs)
        contents = [doc.get_content(MetadataMode.EMBED) for doc in docs]
        assert contents == [doc.get_content(MetadataMode.LLM) for doc in docs]
        ids = [doc.node_id for doc in docs]
    assert ids == [stable_chunk_id(c) for c in chunks]
    assert contents == [c.contextualized_text if contextualized else c.text for c in chunks]
    snapshots = [chunk_from_dict(doc.metadata["omnichunk"]) for doc in docs]
    assert snapshots == chunks
    assert_source(snapshots, loaded)
    for chunk in snapshots:
        for element in references(chunk):
            # Resolve the actual JSON pointer, not a fabricated source identifier.
            collection, offset = element["element_id"][2:].split("/")
            upstream = payload[collection][int(offset)]
            assert upstream["self_ref"] == element["element_id"]
            for prov in element["metadata"]["provenance"]:
                assert str(prov["page_no"]) in payload["pages"]
            table = element["metadata"].get("table")
            if table:
                for row in table["rows"]:
                    for cell in row["cells"]:
                        original = upstream["data"]["table_cells"][
                            int(cell["cell_ref"].split("/")[-1])
                        ]
                        br = cell["byte_range"]
                        assert (
                            loaded.text.encode()[br["start"] : br["end"]].decode()
                            == original["text"]
                        )


def test_missing_provenance_identity_revision_and_page_size_remain_explicit(payload):
    payload["origin"] = None
    payload["pages"] = {}
    loaded = load_docling_document(payload)
    chunks = chunk_loaded_document("fallback.pdf", loaded, OPTIONS)
    assert all(
        c.source.source_id == "fallback.pdf"
        and c.source.metadata["extraction_revision"] is None
        and c.source.metadata["origin"] is None
        for c in chunks
    )
    metadata = [r["metadata"] for c in chunks for r in references(c)]
    assert any(m["provenance"] == [] and m["provenance_status"] == "missing" for m in metadata)
    assert all(p["page_size"] is None for m in metadata for p in m["provenance"])
    overridden = chunk_loaded_document(
        "fallback.pdf", loaded, replace(OPTIONS, source_id="override")
    )
    assert all(c.source.source_id == "override" for c in overridden)


@pytest.mark.parametrize("version", [None, "1.0.0", "1.11.0", "2.0.0", 1])
def test_unsupported_schema_is_rejected_before_docling_can_upgrade_it(payload, version):
    payload["version"] = version
    with pytest.raises(ChunkingError, match="Unsupported Docling schema"):
        load(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "text",
        "reference",
        "unreachable",
        "cell_bounds",
        "cell_span",
        "cell_overlap",
        "nan",
        "rich_cell",
        "negative_dimensions",
        "element_id",
    ],
)
def test_malformed_or_unsupported_content_is_not_silently_dropped(payload, mutation):
    cell = payload["tables"][0]["data"]["table_cells"][0]
    if mutation == "text":
        del payload["texts"][0]["text"]
    elif mutation == "reference":
        payload["body"]["children"][0]["cref"] = "#/texts/999"
    elif mutation == "unreachable":
        payload["body"]["children"].pop()
    elif mutation == "cell_bounds":
        cell["end_row_offset_idx"] = 99
    elif mutation == "cell_span":
        cell["row_span"] = 2
    elif mutation == "cell_overlap":
        payload["tables"][0]["data"]["table_cells"].append(deepcopy(cell))
    elif mutation == "nan":
        payload["texts"][0]["prov"][0]["bbox"]["t"] = float("nan")
    elif mutation == "rich_cell":
        cell["ref"] = {"cref": "#/texts/0"}
    elif mutation == "element_id":
        payload["texts"][0]["self_ref"] = "#/texts/123"
    else:
        payload["tables"][0]["data"]["num_rows"] = -1
    with pytest.raises(ChunkingError, match="Malformed Docling document"):
        load(payload)


def test_actual_environment_without_docling_supports_core_and_actionable_import_error():
    code = """
import importlib.util, sys
sys.path.insert(0, sys.argv[1])
assert importlib.util.find_spec("docling_core") is None
from omnichunk import Chunker, load_docling_document, chunk_from_dict
assert Chunker().chunk("doc.txt", "Türkçe 你好 👩‍💻")
try:
    load_docling_document({})
except ImportError as error:
    assert "omnichunk[docling]" in str(error)
else:
    raise AssertionError("Optional dependency unexpectedly imported")
"""
    result = subprocess.run(
        [sys.executable, "-S", "-c", code, str(FIXTURE.parents[2] / "src")],
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_option_and_input_type_errors(payload):
    with pytest.raises(ChunkingError, match="Expected a DoclingDocument"):
        load_docling_document("not a document")
    for kwargs in [{"source_id": ""}, {"extraction_revision": 12}]:
        with pytest.raises(ValueError, match="nonempty string"):
            load_docling_document(payload, **kwargs)
    payload["schema_name"] = "AnotherDocument"
    with pytest.raises(ChunkingError, match="Unsupported Docling schema"):
        load(payload)


def test_llamaindex_export_default_metadata_rendering_is_unchanged(payload):
    pytest.importorskip("llama_index.core")
    chunks = chunk_loaded_document("g.pdf", load(payload), OPTIONS)
    default = chunks_to_llamaindex_docs(chunks)[0]
    assert default.excluded_embed_metadata_keys == ["omnichunk"]
    assert default.excluded_llm_metadata_keys == ["omnichunk"]


def test_merged_sparse_and_empty_tables_preserve_identity_without_duplicating_source():
    schema = pytest.importorskip("docling_core.types.doc")
    document = schema.DoclingDocument(name="Sparse and merged")
    table = document.add_table(
        data=schema.TableData(
            num_rows=3,
            num_cols=3,
            table_cells=[
                schema.TableCell(
                    text="Both",
                    row_span=2,
                    col_span=2,
                    start_row_offset_idx=0,
                    end_row_offset_idx=2,
                    start_col_offset_idx=0,
                    end_col_offset_idx=2,
                    column_header=True,
                ),
                schema.TableCell(
                    text="one\tinline\nnewline",
                    start_row_offset_idx=2,
                    end_row_offset_idx=3,
                    start_col_offset_idx=2,
                    end_col_offset_idx=3,
                ),
            ],
        )
    )
    document.add_table(data=schema.TableData(num_rows=2, num_cols=0))
    document.add_table(data=schema.TableData())
    loaded = load_docling_document(
        document, source_id="manual:17", extraction_revision="extract:v1"
    )
    assert loaded.text == "Both\t\t\n\t\t\n\t\tone\tinline\nnewline\n\n\n"
    assert loaded.text.count("Both") == 1
    merged = loaded.elements[0].metadata["table"]["rows"][1]["cells"][0]
    assert merged["cell_ref"] == table.self_ref + "/data/table_cells/0"
    assert merged["row_end"] == merged["col_end"] == 2
    chunks = chunk_loaded_document(
        "sparse.pdf", loaded, replace(OPTIONS, max_chunk_size=16, context_mode="none")
    )
    assert_source(chunks, loaded)
    assert (
        chunk_loaded_document(
            "empty.pdf", load_docling_document(schema.DoclingDocument(name="Empty")), OPTIONS
        )
        == []
    )


def test_original_boxes_are_preserved_even_when_docling_clamps_a_copy(payload):
    # Schema accepts a small tolerance beyond the page edge and normalizes it.
    payload["texts"][0]["prov"][0]["bbox"]["l"] = -0.01
    payload["texts"][0]["prov"][0]["bbox"].pop("coord_origin")
    original = deepcopy(payload)
    loaded = load(payload)
    box = loaded.elements[0].metadata["provenance"][0]["bbox"]
    assert box["l"] == -0.01
    assert box["coord_origin"] == "TOPLEFT"
    assert payload == original


def test_unsupported_picture_is_an_explicit_error():
    schema = pytest.importorskip("docling_core.types.doc")
    document = schema.DoclingDocument(name="Picture")
    document.add_picture()
    with pytest.raises(ChunkingError, match="Unsupported non-text/table"):
        load_docling_document(document)


def test_lossless_whitespace_elements_and_source_uri_fallback(payload):
    schema = pytest.importorskip("docling_core.types.doc")
    document = schema.DoclingDocument(name="Whitespace")
    document.add_text(label=schema.DocItemLabel.PARAGRAPH, text=" \t")
    loaded = load_docling_document(document)
    chunks = chunk_loaded_document("space.pdf", loaded, OPTIONS)
    assert "".join(c.text for c in chunks) == loaded.text
    assert references(chunks[0])[0]["metadata"]["provenance"] == []
    assert (
        chunk_loaded_document("space.pdf", loaded, replace(OPTIONS, coverage_policy="retrieval"))
        == []
    )
    with_uri = load_docling_document(payload)
    assert with_uri.source_id == payload["origin"]["uri"]


def test_loaded_identity_fallback_does_not_bypass_explicit_invalid_options(payload):
    with pytest.raises(ValueError, match="source_id"):
        chunk_loaded_document("g.pdf", load(payload), replace(OPTIONS, source_id=""))


def test_overlap_retains_first_elements_heading_context():
    schema = pytest.importorskip("docling_core.types.doc")
    document = schema.DoclingDocument(name="Heading boundary")
    document.add_text(label=schema.DocItemLabel.PARAGRAPH, text="Before the heading.")
    document.add_heading("Heading", level=1)
    document.add_text(label=schema.DocItemLabel.PARAGRAPH, text="After the heading.")
    loaded = load_docling_document(document)
    chunks = chunk_loaded_document(
        "g.pdf", loaded, replace(OPTIONS, overlap=12, context_mode="none")
    )
    crossed = [c for c in chunks if len(references(c)) == 3]
    assert crossed
    assert crossed[0].context.heading_hierarchy == []
    assert references(crossed[0])[1]["metadata"]["heading_hierarchy"] == ["Heading"]


def test_large_table_header_associations_and_row_buckets_use_real_schema():
    schema = pytest.importorskip("docling_core.types.doc")
    document = schema.DoclingDocument(name="Large ordinary table")
    document.add_table(
        data=schema.TableData(
            num_rows=4000,
            num_cols=3,
            table_cells=[
                schema.TableCell(
                    text=f"{row}:{col}",
                    start_row_offset_idx=row,
                    end_row_offset_idx=row + 1,
                    start_col_offset_idx=col,
                    end_col_offset_idx=col + 1,
                    column_header=row == 0,
                    row_header=col == 0 and row > 0,
                )
                for row in range(4000)
                for col in range(3)
            ],
        )
    )
    loaded = load_docling_document(document)
    rows = loaded.elements[0].metadata["table"]["rows"]
    assert len(rows) == 4000
    assert loaded.text.count("3999:2") == 1
    for row_index in (1, 1999, 3999):
        assert len(rows[row_index]["cells"]) == 3
        assert rows[row_index]["cells"][2]["header_cell_refs"] == [
            "#/tables/0/data/table_cells/2",
            f"#/tables/0/data/table_cells/{row_index * 3}",
        ]
