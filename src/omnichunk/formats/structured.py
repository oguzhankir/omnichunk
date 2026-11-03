"""Range projection and row proposals for explicitly loaded structured documents."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from typing import Any

from omnichunk.context.format import format_contextualized_text
from omnichunk.formats.types import FormatSegment, LoadedDocument
from omnichunk.sizing.counter import make_size_counter
from omnichunk.types import ByteRange, Chunk, ChunkContext, ChunkOptions, LineRange


def _intersection(reference: dict[str, Any], span: ByteRange) -> dict[str, Any] | None:
    start, end = reference["byte_range"]["start"], reference["byte_range"]["end"]
    # Empty cells still have a known insertion point in the canonical row.
    if start == end:
        return {"start": start, "end": end} if span.start <= start < span.end else None
    if start < span.end and end > span.start:
        return {"start": max(start, span.start), "end": min(end, span.end)}
    return None


def _locate(reference: dict[str, Any], span: ByteRange) -> dict[str, Any]:
    intersection = _intersection(reference, span)
    return {
        **deepcopy(reference),
        "chunk_byte_range": intersection,
        "is_partial": intersection != reference["byte_range"],
    }


def element_context(
    context: ChunkContext, span: ByteRange, loaded: LoadedDocument, raw: bytes | None = None
) -> ChunkContext:
    """Select provenance again after final splitting, filling gaps or adding overlap.

    Page geometry stays at the granularity supplied by extraction. We do not
    interpolate boxes for text fragments or infer a page for table-cell boxes.
    """
    elements: list[dict[str, Any]] = []
    headers = []
    header_text = []
    headings: list[str] = []
    raw = loaded.text.encode("utf-8") if raw is None else raw
    for element in loaded.elements:
        reference = {
            "element_id": element.element_id,
            "kind": element.kind,
            "byte_range": {"start": element.byte_range.start, "end": element.byte_range.end},
            "metadata": {key: value for key, value in element.metadata.items() if key != "table"},
        }
        if _intersection(reference, span) is None:
            continue
        located = _locate(reference, span)
        metadata = located["metadata"]
        if not elements:
            headings = list(metadata.get("heading_hierarchy", []))
        table = element.metadata.get("table")
        if table is not None:
            rows = []
            for row in table["rows"]:
                if _intersection(row, span) is not None:
                    selected = _locate(row, span)
                    selected["cells"] = [_locate(cell, span) for cell in row["cells"]]
                    rows.append(selected)
                elif (
                    row["row_index"] in table["header_rows"]
                    and row["byte_range"]["end"] <= span.start
                ):
                    headers.append(
                        {
                            "element_id": element.element_id,
                            "row_index": row["row_index"],
                            "byte_range": row["byte_range"],
                        }
                    )
                    r = row["byte_range"]
                    header_text.append(raw[r["start"] : r["end"]].decode("utf-8"))
            metadata["table"] = {
                **{key: deepcopy(value) for key, value in table.items() if key != "rows"},
                "rows": rows,
            }
        elements.append(located)
    metadata = {**context.format_metadata, "elements": elements}
    # Recompute rather than inherit context from a neighboring engine candidate.
    metadata.pop("table_context", None)
    if headers:
        metadata["table_context"] = {"headers": headers, "text": "".join(header_text)}
    return replace(context, heading_hierarchy=headings, format_metadata=metadata)


def table_chunks(
    filepath: str, segment: FormatSegment, loaded: LoadedDocument, options: ChunkOptions
) -> Iterator[Chunk]:
    """Pack complete rows using the rendered counter; finalization owns overflow.

    An oversized row is proposed intact. Shared finalization then splits it,
    raises, or preserves it according to the existing overflow policy.
    """
    size = make_size_counter(options.size_unit, options.tokenizer)
    raw = loaded.text.encode("utf-8")
    context = ChunkContext(
        filepath=filepath,
        section_type="table",
        parse_errors=[f"{loaded.format_name} loader: {warning}" for warning in loaded.warnings],
        format_metadata={"source_format": loaded.format_name},
    )

    def candidate(start: int, end: int) -> Chunk:
        text = raw[start:end].decode("utf-8")
        return Chunk(text, text, ByteRange(start, end), LineRange(0, 0), 0, -1, context)

    start: int | None = None
    end = 0
    for row in segment.metadata["row_ranges"]:
        row_start, row_end = row["start"], row["end"]
        trial_start = row_start if start is None else start
        text = raw[trial_start:row_end].decode("utf-8")
        projected = element_context(context, ByteRange(trial_start, row_end), loaded, raw)
        rendered = (
            text if options.context_mode == "none" else format_contextualized_text(text, projected)
        )
        if start is not None and size(rendered) > options.max_chunk_size:
            yield candidate(start, end)
            start = row_start
        elif start is None:
            start = row_start
        end = row_end
    if start is not None:
        yield candidate(start, end)
