from __future__ import annotations

import json
from typing import Any

from omnichunk.formats.types import FormatSegment, LoadedDocument


def load_ipynb(content: str) -> LoadedDocument:
    """Parse a Jupyter notebook JSON string into canonical text and segments."""
    warnings: list[str] = []
    try:
        data: dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as exc:
        return LoadedDocument(
            text="",
            segments=(),
            format_name="ipynb",
            warnings=(f"invalid_json: {exc}",),
        )

    cells = data.get("cells")
    if not isinstance(cells, list):
        return LoadedDocument(
            text="",
            segments=(),
            format_name="ipynb",
            warnings=("missing_or_invalid_cells",),
        )

    parts: list[str] = []
    segments: list[FormatSegment] = []
    cursor = 0

    for idx, cell in enumerate(cells):
        if not isinstance(cell, dict):
            warnings.append(f"cell_{idx}_not_object")
            continue

        ctype = str(cell.get("cell_type", "") or "")
        src = cell.get("source", "")
        cell_text = "".join(str(x) for x in src) if isinstance(src, list) else str(src)

        if ctype == "markdown":
            if cell_text:
                start = cursor
                parts.append(cell_text)
                cursor += len(cell_text)
                segments.append(
                    FormatSegment(
                        char_start=start,
                        char_end=cursor,
                        kind="prose",
                        metadata={"cell": idx, "cell_type": "markdown"},
                    )
                )
        elif ctype == "code":
            lang = _code_language(cell)
            if cell_text:
                start = cursor
                parts.append(cell_text)
                cursor += len(cell_text)
                segments.append(
                    FormatSegment(
                        char_start=start,
                        char_end=cursor,
                        kind="code",
                        metadata={"cell": idx, "cell_type": "code", "language": lang},
                    )
                )
            out_text = _extract_cell_outputs(cell)
            if out_text.strip():
                start = cursor
                parts.append(out_text)
                cursor += len(out_text)
                segments.append(
                    FormatSegment(
                        char_start=start,
                        char_end=cursor,
                        kind="prose",
                        metadata={"cell": idx, "cell_type": "output"},
                    )
                )
        elif ctype == "raw":
            if cell_text:
                start = cursor
                parts.append(cell_text)
                cursor += len(cell_text)
                segments.append(
                    FormatSegment(
                        char_start=start,
                        char_end=cursor,
                        kind="prose",
                        metadata={"cell": idx, "cell_type": "raw"},
                    )
                )
        else:
            warnings.append(f"unknown_cell_type:{ctype}")

    full_text = "".join(parts)
    return LoadedDocument(
        text=full_text,
        segments=tuple(segments),
        format_name="ipynb",
        warnings=tuple(warnings),
    )


def _code_language(cell: dict[str, Any]) -> str:
    meta = cell.get("metadata")
    if isinstance(meta, dict):
        lang = meta.get("language")
        if isinstance(lang, str) and lang:
            return lang
    return "python"


def _extract_cell_outputs(cell: dict[str, Any]) -> str:
    outputs = cell.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        return ""

    lines: list[str] = []
    for out in outputs:
        if not isinstance(out, dict):
            continue
        otype = str(out.get("output_type", "") or "")
        if otype == "stream":
            text = out.get("text", "")
            if isinstance(text, list):
                lines.append("".join(str(x) for x in text))
            else:
                lines.append(str(text))
        elif otype in ("display_data", "execute_result"):
            data = out.get("data")
            if isinstance(data, dict):
                plain = data.get("text/plain")
                if isinstance(plain, list):
                    lines.append("".join(str(x) for x in plain))
                elif isinstance(plain, str):
                    lines.append(plain)
        elif otype == "error":
            tb = out.get("traceback")
            if isinstance(tb, list):
                lines.append("\n".join(str(x) for x in tb))
        # Skip binary image/svg-heavy payloads deterministically

    if not lines:
        return ""

    return "[output]\n" + "\n".join(lines) + "\n"
