from __future__ import annotations

import io
from typing import Any

from omnichunk.formats.types import FormatSegment, LoadedDocument


def load_docx_bytes(raw: bytes) -> LoadedDocument:
    """Extract text from DOCX bytes into prose segments (paragraphs and tables)."""
    try:
        from docx import Document
        from docx.oxml.table import CT_Tbl
        from docx.oxml.text.paragraph import CT_P
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise ImportError(
            "DOCX support requires python-docx. Install with: pip install omnichunk[docx]"
        ) from exc

    warnings: list[str] = []
    document = Document(io.BytesIO(raw))

    def iter_block_items(parent: Any) -> Any:
        parent_elm = parent.element.body
        for child in parent_elm.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent)

    parts: list[str] = []
    segments: list[FormatSegment] = []
    cursor = 0
    block_index = 0

    for block in iter_block_items(document):
        if isinstance(block, Paragraph):
            ptext = block.text
            if not ptext.strip():
                block_index += 1
                continue
            style_name = ""
            try:
                style_name = block.style.name if block.style is not None else ""
            except Exception:
                warnings.append(f"paragraph_style_{block_index}")
            start = cursor
            chunk = ptext + "\n\n"
            parts.append(chunk)
            cursor += len(chunk)
            meta: dict[str, Any] = {"docx_block": "paragraph", "index": block_index}
            if style_name and "Heading" in style_name:
                meta["heading_style"] = style_name
            segments.append(
                FormatSegment(
                    char_start=start,
                    char_end=cursor,
                    kind="prose",
                    metadata=meta,
                )
            )
        else:
            table = block
            rows_text: list[str] = []
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells]
                rows_text.append("\t".join(cells))
            tbl = "\n".join(rows_text) + "\n\n"
            if not tbl.strip():
                block_index += 1
                continue
            start = cursor
            parts.append(tbl)
            cursor += len(tbl)
            segments.append(
                FormatSegment(
                    char_start=start,
                    char_end=cursor,
                    kind="prose",
                    metadata={"docx_block": "table", "index": block_index},
                )
            )
        block_index += 1

    full_text = "".join(parts)
    return LoadedDocument(
        text=full_text,
        segments=tuple(segments),
        format_name="docx",
        warnings=tuple(warnings),
    )
