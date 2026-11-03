"""Optional adapter for already-extracted DoclingDocument schema 1.10.0.

Only docling-core is used. Conversion, OCR, image interpretation and models stay
with the caller. Imports are lazy so core installation remains dependency-free.
"""

from __future__ import annotations

import importlib
import json
import warnings
from copy import deepcopy
from typing import Any, Literal

from omnichunk.formats.types import DocumentElement, FormatSegment, LoadedDocument
from omnichunk.types import ByteRange, ChunkingError

DOCLING_SCHEMA_VERSION = "1.10.0"


def load_docling_document(
    document: object, *, source_id: str | None = None, extraction_revision: str | None = None
) -> LoadedDocument:
    """Load a real DoclingDocument or its exported dictionary into canonical text.

    Supports docling-core 2.105.0 / schema 1.10.0. Text fields are retained verbatim
    with two newlines between text elements. Tables use tabs between columns and
    one newline per row; merged cell text appears once at its start coordinate.
    List markers remain metadata. References and geometry address the supplied
    extraction; canonical ranges address only the resulting UTF-8 text.

    Missing origin, extraction revision, page size and geometry remain explicit
    nulls/empty lists. Unsupported structures and malformed input raise
    ChunkingError rather than being silently dropped.
    """
    try:
        schema = importlib.import_module("docling_core.types.doc")
    except ImportError as exc:
        raise ImportError(
            "Docling support requires docling-core. Install with: pip install omnichunk[docling]"
        ) from exc
    for name, value in [("source_id", source_id), ("extraction_revision", extraction_revision)]:
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be a nonempty string or None")
    if isinstance(document, schema.DoclingDocument):
        # Exclude the computed grid: it duplicates cells and invents sparse cells.
        raw = document.model_dump(mode="json", exclude={"tables": {"__all__": {"data": {"grid"}}}})
    elif isinstance(document, dict):
        raw = deepcopy(document)
    else:
        raise ChunkingError("Expected a DoclingDocument or its exported dictionary")
    if raw.get("schema_name") != "DoclingDocument" or raw.get("version") != DOCLING_SCHEMA_VERSION:
        raise ChunkingError(
            f"Unsupported Docling schema; expected DoclingDocument {DOCLING_SCHEMA_VERSION}"
        )
    try:
        raw = json.loads(json.dumps(raw, allow_nan=False))
        # Validate a copy: Docling may normalize/clamp boxes. Preserve supplied
        # geometry in our records and never mutate the caller's extraction.
        validated = schema.DoclingDocument.model_validate(deepcopy(raw))
        return _load(validated, raw, schema, source_id, extraction_revision)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        raise ChunkingError(f"Malformed Docling document: {exc}") from exc


def _range(start: int, end: int) -> dict[str, int]:
    return {"start": start, "end": end}


def _bbox(box: dict[str, Any] | None) -> dict[str, Any] | None:
    # TOPLEFT is the declared BoundingBox default in schema 1.10.0.
    return {"coord_origin": "TOPLEFT", **box} if box is not None else None


def _load(
    document: Any,
    raw: dict[str, Any],
    schema: Any,
    source_id: str | None,
    extraction_revision: str | None,
) -> LoadedDocument:
    unsupported = ("pictures", "key_value_items", "form_items", "field_regions", "field_items")
    if any(raw.get(collection) for collection in unsupported):
        raise ValueError("Unsupported non-text/table Docling elements")
    parts: list[str] = []
    segments: list[FormatSegment] = []
    elements: list[DocumentElement] = []
    cursor = 0
    byte_cursor = 0
    headings: list[tuple[int, str]] = []
    seen: set[str] = set()
    originals = {item["self_ref"]: item for key in ("texts", "tables") for item in raw.get(key, [])}
    for collection in ("texts", "tables"):
        for offset, original in enumerate(raw.get(collection, [])):
            if original["self_ref"] != f"#/{collection}/{offset}":
                raise ValueError("Element self_ref does not resolve to its original array position")
    # furniture is deprecated by Docling but remains part of schema 1.10.0.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        roots = (document.body, document.furniture)
    for root in roots:
        for item, _ in document.iterate_items(
            root=root, traverse_pictures=True, included_content_layers=set(schema.ContentLayer)
        ):
            if not isinstance(item, (schema.TextItem, schema.TableItem)):
                raise ValueError(f"Unsupported Docling element: {item.self_ref}")
            seen.add(item.self_ref)
            original = originals[item.self_ref]
            label = item.label.value
            if isinstance(item, schema.SectionHeaderItem) or label == "title":
                level = item.level if isinstance(item, schema.SectionHeaderItem) else 0
                headings = [(n, title) for n, title in headings if n < level]
                headings.append((level, item.text))
            provenance = []
            for prov in original.get("prov", []):
                page = raw.get("pages", {}).get(str(prov["page_no"]))
                if page is None:
                    page = raw.get("pages", {}).get(prov["page_no"])
                provenance.append(
                    {
                        "page_no": prov["page_no"],
                        "bbox": _bbox(prov["bbox"]),
                        "docling_charspan": prov["charspan"],
                        "page_size": page["size"] if page is not None else None,
                        "coordinate_units": None,
                    }
                )
            metadata: dict[str, Any] = {
                "provenance": provenance,
                "provenance_status": "available" if provenance else "missing",
                "parent_ref": original.get("parent", {}).get("cref")
                if original.get("parent")
                else None,
                "heading_hierarchy": [title for _, title in headings],
            }
            kind: Literal["prose", "code", "table"] = "prose"
            segment_metadata: dict[str, Any] = {}
            if isinstance(item, schema.TableItem):
                kind = "table"
                text, table = _table(original, byte_cursor)
                metadata["table"] = table
                segment_metadata["row_ranges"] = [row["byte_range"] for row in table["rows"]]
            else:
                text = item.text + "\n\n"
                metadata["text_byte_range"] = _range(
                    byte_cursor, byte_cursor + len(item.text.encode("utf-8"))
                )
                if isinstance(item, schema.ListItem):
                    metadata["list"] = {"marker": item.marker, "enumerated": item.enumerated}
                if isinstance(item, schema.CodeItem):
                    kind = "code"
                    metadata["code_language"] = item.code_language.value
                    # Unknown extraction language stays plaintext; never guess a grammar.
                    segment_metadata["language"] = "plaintext"
            end = cursor + len(text)
            byte_end = byte_cursor + len(text.encode("utf-8"))
            elements.append(
                DocumentElement(item.self_ref, ByteRange(byte_cursor, byte_end), label, metadata)
            )
            # Adjacent prose elements share an engine segment, permitting a chunk
            # to retain several page/element references without flattening lineage.
            boundary = label in ("section_header", "title")
            if segments and kind == "prose" and segments[-1].kind == "prose" and not boundary:
                previous = segments[-1]
                segments[-1] = FormatSegment(previous.char_start, end, kind)
            else:
                segments.append(FormatSegment(cursor, end, kind, segment_metadata))
            parts.append(text)
            cursor, byte_cursor = end, byte_end
    if seen != set(originals):
        raise ValueError("Unreachable text/table elements in Docling document")
    origin = raw.get("origin")
    return LoadedDocument(
        "".join(parts),
        tuple(segments),
        "docling",
        source_id=source_id or (origin.get("uri") if origin else None),
        metadata={
            "docling_schema_version": raw["version"],
            "extraction_revision": extraction_revision,
            "origin": origin,
        },
        elements=tuple(elements),
    )


def _table(original: dict[str, Any], start: int) -> tuple[str, dict[str, Any]]:
    data = original["data"]
    nrows, ncols = data["num_rows"], data["num_cols"]
    if type(nrows) is not int or type(ncols) is not int or nrows < 0 or ncols < 0:
        raise ValueError("Invalid table dimensions")
    cells = []
    occupied: set[tuple[int, int]] = set()
    for i, cell in enumerate(data.get("table_cells", [])):
        if "ref" in cell:
            raise ValueError("RichTableCell is not supported in this Docling slice")
        r, re = cell["start_row_offset_idx"], cell["end_row_offset_idx"]
        c, ce = cell["start_col_offset_idx"], cell["end_col_offset_idx"]
        if not (0 <= r < re <= nrows and 0 <= c < ce <= ncols):
            raise ValueError("Table cell outside declared dimensions")
        if cell.get("row_span", 1) != re - r or cell.get("col_span", 1) != ce - c:
            raise ValueError("Table cell span disagrees with offsets")
        positions = {(row, col) for row in range(r, re) for col in range(c, ce)}
        if occupied & positions:
            raise ValueError("Overlapping table cells")
        occupied.update(positions)
        cells.append(
            {
                "cell_ref": f"{original['self_ref']}/data/table_cells/{i}",
                "row_start": r,
                "row_end": re,
                "col_start": c,
                "col_end": ce,
                "column_header": cell.get("column_header", False),
                "row_header": cell.get("row_header", False),
                "row_section": cell.get("row_section", False),
                "bbox": _bbox(cell.get("bbox")),
                "page_no": None,
                "coordinate_units": None,
                "text": cell["text"],
            }
        )
    starting_by_row: dict[int, dict[int, Any]] = {}
    spanning_by_row: dict[int, list[Any]] = {}
    column_headers: dict[int, list[Any]] = {}
    row_headers: dict[int, list[Any]] = {}
    order = {cell["cell_ref"]: i for i, cell in enumerate(cells)}
    for cell in cells:
        starting_by_row.setdefault(cell["row_start"], {})[cell["col_start"]] = cell
        for row_index in range(cell["row_start"], cell["row_end"]):
            spanning_by_row.setdefault(row_index, []).append(cell)
            if cell["row_header"]:
                row_headers.setdefault(row_index, []).append(cell)
        if cell["column_header"]:
            for col_index in range(cell["col_start"], cell["col_end"]):
                column_headers.setdefault(col_index, []).append(cell)
    parts = []
    rows = []
    cursor = start
    for row_index in range(nrows):
        row_start = cursor
        starting = starting_by_row.get(row_index, {})
        for col_index in range(ncols):
            cell = starting.get(col_index)
            if cell is not None:
                text = cell.pop("text")
                cell["byte_range"] = _range(cursor, cursor + len(text.encode("utf-8")))
                parts.append(text)
                cursor += len(text.encode("utf-8"))
            separator = "\n" if col_index == ncols - 1 else "\t"
            parts.append(separator)
            cursor += 1
        if ncols == 0:
            parts.append("\n")
            cursor += 1
        rows.append(
            {
                "row_index": row_index,
                "byte_range": _range(row_start, cursor),
                "cells": spanning_by_row.get(row_index, []),
            }
        )
    for cell in cells:
        candidates = {
            header["cell_ref"]: header
            for col_index in range(cell["col_start"], cell["col_end"])
            for header in column_headers.get(col_index, [])
            if header["row_start"] < cell["row_start"]
        }
        candidates.update(
            {
                header["cell_ref"]: header
                for header in row_headers.get(cell["row_start"], [])
                if header["col_start"] < cell["col_start"]
            }
        )
        candidates.pop(cell["cell_ref"], None)
        # A merged header can match several columns. Deduplicate while retaining
        # the original table_cells order used by existing provenance records.
        cell["header_cell_refs"] = sorted(candidates, key=order.__getitem__)
    return "".join(parts), {
        "num_rows": nrows,
        "num_cols": ncols,
        "orientation": data.get("orientation", "rot_0"),
        "header_association": "flags_and_spans",
        "header_rows": sorted({cell["row_start"] for cell in cells if cell["column_header"]}),
        "rows": rows,
    }
