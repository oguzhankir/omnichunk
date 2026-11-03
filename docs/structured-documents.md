# Extracted Docling documents

Use `load_docling_document()` when extraction has already produced a Docling
document. This first M3 slice handles text, headings, lists, code and ordinary
tables; it does not perform conversion, OCR or image interpretation. It adds no
mandatory core dependencies and does not change PDF/DOCX file loading.

```bash
pip install "omnichunk[docling,langchain,llamaindex]"
# From this checkout:
python examples/docling_provenance.py
```

The optional `docling` extra pins **docling-core 2.105.0**, supporting Python
3.10+ and **DoclingDocument schema 1.10.0**. This deliberately narrow initial
compatibility boundary was exercised with the real library. Other schema versions
are rejected before Docling can silently upgrade them. Supply a native
`DoclingDocument` or its exported dictionary, not a `ConversionResult`, file bytes
or a filename. Pictures, form/key-value elements, rich table cells and unreachable
text/table elements raise `ChunkingError`. Ordinary merged and sparse cells are
supported. This is a bounded contribution; other M3 work remains open.

## Chunk an extraction once

```python
import json
from pathlib import Path
from omnichunk import ChunkOptions, chunk_loaded_document, load_docling_document

extracted = json.loads(Path("extracted.json").read_text(encoding="utf-8"))
loaded = load_docling_document(
    extracted, source_id="manual:operations", extraction_revision="extractor:2026-11-v1"
)
chunks = chunk_loaded_document(
    "operations.pdf", loaded,
    ChunkOptions(max_chunk_size=800, min_chunk_size=0, coverage_policy="lossless"),
)
assert "".join(chunk.text for chunk in chunks) == loaded.text
```

The adapter visits the validated body tree in order, then the legacy furniture
tree, including all content layers. Text fields remain verbatim and each receives
two trailing newlines. List markers remain metadata. Code is routed through the
existing code engine as plaintext while the original extraction language is
retained. Tables use tabs between columns and one newline per row, including empty
cells. Cell text is emitted once at its starting row/column; merged/sparse positions
have empty slots. Embedded tabs/newlines in cell text are preserved, so use the
cell ranges to resolve cells instead of reparsing the text as CSV/TSV.

These delimiters define the **canonical extracted text**. Keep `loaded.text` and
the original extraction for later citation resolution. No byte range addresses a
PDF/DOCX binary, and the canonical SHA-256 `source.revision` is distinct from
`source.metadata["extraction_revision"]`. That extraction revision is caller-supplied
and is `None` when absent. The original Docling `origin` is retained independently.
Identity precedence is `ChunkOptions.source_id`, adapter `source_id`, original
`origin.uri`, then the filepath label. Supply a stable logical ID for sources that
may move.

## Resolve elements, pages and geometry

Every finalized chunk carries `context.format_metadata["elements"]`. Selection is
recomputed after splits, whitespace filling and numeric overlap, so a chunk can
retain references to several elements and pages. Each record has:

| Field | Meaning |
| --- | --- |
| `element_id` | Original Docling `self_ref`, such as `#/texts/2`; missing IDs in a Docling document are invalid. |
| `kind` | Original extraction label, such as `section_header`, `paragraph`, `list_item`, `code` or `table`. |
| `byte_range` | Complete element range in canonical UTF-8 text, including its delimiters. |
| `chunk_byte_range` | Intersection with this chunk's canonical range. |
| `is_partial` | Whether the intersection differs from the complete element range. |
| `metadata.provenance` | Original page number, bounding box and `docling_charspan`, with available page size. Empty when absent. |
| `metadata.provenance_status` | `"available"` or `"missing"`. |
| `metadata.heading_hierarchy` | Owning extracted headings. The first intersecting element also supplies the chunk heading context. |
| `metadata.list` | Original list `marker` and `enumerated` flag, when supplied. |
| `metadata.table` | Table dimensions/orientation, header rows and intersecting row/cell records. |

`metadata.text_byte_range` addresses only a text element's actual text, excluding
the appended delimiters. `docling_charspan` stays in its original extraction
coordinate space; it is not a canonical byte range. Bounding-box numbers and
`coord_origin` (`TOPLEFT`/`BOTTOMLEFT`) are retained without clipping or interpolation
for fragments. An omitted origin uses Docling's declared `TOPLEFT` schema default.
`coordinate_units=None` records that this schema does not declare a physical unit.
Page sizes can be absent even when a page reference exists. Geometry remains at
element granularity, so a fragment of a multi-page element retains all its supplied
page provenance; it does not claim a more precise page/region match.

Cell `cell_ref` values are JSON pointers into the original `table_cells` array.
Rows use original zero-based `row_index`; cells retain half-open row/column spans,
header flags and canonical ranges. `header_cell_refs` associates preceding column
headers and applicable row headers by their supplied flags and intersecting spans;
`header_association="flags_and_spans"` identifies this deterministic derivation.
Missing sparse positions do not acquire invented cell IDs. Cell boxes preserve
their supplied origin, with `page_no=None`: Docling's cell schema has no page field,
so the adapter does not assign a table page to a cell. A cell carried for row
context can have `chunk_byte_range=None` when its source text is outside the chunk.

## Table context and budgets

Tables form separate segments. Complete fitting rows are packed using the
configured counter on the complete rendered payload. Preceding header rows are
repeated in `contextualized_text` as `# Table headers (derived)`, with their original
row/element/range references under `context.format_metadata["table_context"]`.
They never become part of `Chunk.text` or its source range. Metadata alone is not
rendered or counted as text.

An oversized row follows the existing `overflow_policy`: `split` emits exact
Unicode source fragments with partial row/cell metadata, `error` rejects it, and
`preserve` retains it with measured overflow diagnostics. Nothing is truncated.
`context_mode="none"` renders only source text. Under `context_overflow="omit"`,
context that cannot fit is omitted with `metadata["context_omitted"]`; references
and header context remain in metadata. `context_overflow="error"` rejects it.
Numeric/line overlap and nonadditive custom counters still use shared finalization
and the [existing budget contracts](reference/contracts.md).

## JSON and framework conversion

```python
import json
from omnichunk import chunk_from_dict
from omnichunk.serialization import (
    chunks_to_jsonl, chunks_to_langchain_docs, chunks_to_llamaindex_docs,
)

restored = [chunk_from_dict(json.loads(line)) for line in chunks_to_jsonl(chunks).splitlines()]
assert restored == chunks
langchain = chunks_to_langchain_docs(restored)
llamaindex = chunks_to_llamaindex_docs(restored, include_metadata_in_content=False)
for document in [*langchain, *llamaindex]:
    chunk = chunk_from_dict(document.metadata["omnichunk"])
    for reference in chunk.context.format_metadata["elements"]:
        collection, offset = reference["element_id"][2:].split("/")
        original = extracted[collection][int(offset)]
        assert original["self_ref"] == reference["element_id"]
```

Both existing converters keep native chunk IDs, source identity/revisions, ranges,
all element/page/geometry records and table context in their canonical snapshot.
LangChain `page_content` is the selected payload. LlamaIndex adds ordinary metadata
to model rendering by default; use `include_metadata_in_content=False` so its
`MetadataMode.EMBED` and `LLM` content equal that same budgeted payload. The default
is unchanged. Choose `use_contextualized_text=False` on either converter for raw
text. The native framework splitter/parser rejects documents already carrying the
reserved `omnichunk` snapshot: convert these chunks directly instead of chunking
their rendered text again.

The executable example resolves references after both conversions. The authored
fixture tests are offline and use no converter, model downloads or GPU. They are
conformance evidence, not retrieval-quality or production-readiness evidence.

## API

::: omnichunk.formats.load_docling_document

::: omnichunk.formats.DocumentElement
