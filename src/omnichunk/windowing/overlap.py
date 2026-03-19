from __future__ import annotations

from math import floor
from typing import Sequence

from omnichunk.types import ByteRange, Chunk


def build_line_overlap_text(previous_text: str, overlap_lines: int) -> str:
    if overlap_lines <= 0 or not previous_text:
        return ""
    lines = previous_text.splitlines()
    if not lines:
        return ""

    selected: list[str] = []
    for line in reversed(lines):
        if line.strip():
            selected.append(line)
        if len(selected) >= overlap_lines:
            break

    if not selected:
        return "\n".join(lines[-overlap_lines:])

    selected = list(reversed(selected))
    return "\n".join(selected[-overlap_lines:])


def apply_token_overlap(
    chunks: Sequence[Chunk],
    *,
    overlap: int | float,
    max_chunk_size: int,
) -> list[Chunk]:
    """Semchunk-style chunk resequencing with overlap size/ratio."""
    if not chunks:
        return []

    overlap_size = _resolve_overlap(overlap, max_chunk_size)
    if overlap_size <= 0:
        return list(chunks)

    sub_size = min(overlap_size, max(1, max_chunk_size - overlap_size))
    if sub_size <= 0:
        return list(chunks)

    stride = max(1, floor((max_chunk_size - overlap_size) / sub_size))
    width = max(1, floor(max_chunk_size / sub_size))

    out: list[Chunk] = []
    idx = 0
    while idx < len(chunks):
        group = chunks[idx : idx + width]
        if not group:
            break

        first = group[0]
        last = group[-1]
        text = "\n".join(c.text for c in group if c.text)

        out.append(
            Chunk(
                text=text,
                contextualized_text=first.contextualized_text,
                byte_range=ByteRange(first.byte_range.start, last.byte_range.end),
                line_range=first.line_range,
                index=len(out),
                total_chunks=-1,
                context=first.context,
                token_count=sum(c.token_count for c in group),
                char_count=sum(c.char_count for c in group),
                nws_count=sum(c.nws_count for c in group),
            )
        )

        idx += stride

    final_total = len(out)
    out = [
        Chunk(
            text=c.text,
            contextualized_text=c.contextualized_text,
            byte_range=c.byte_range,
            line_range=c.line_range,
            index=i,
            total_chunks=final_total,
            context=c.context,
            token_count=c.token_count,
            char_count=c.char_count,
            nws_count=c.nws_count,
        )
        for i, c in enumerate(out)
    ]
    return out


def _resolve_overlap(overlap: int | float, max_chunk_size: int) -> int:
    if isinstance(overlap, float):
        if overlap <= 0:
            return 0
        if overlap < 1:
            return int(max_chunk_size * overlap)
        return int(overlap)
    return max(0, overlap)
