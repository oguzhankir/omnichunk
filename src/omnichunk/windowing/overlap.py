from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from math import floor

from omnichunk.context.format import format_contextualized_text
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    EntityInfo,
    ImportInfo,
    LineRange,
    SiblingInfo,
)


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
        merged_byte_range = ByteRange(first.byte_range.start, last.byte_range.end)
        text = "".join(c.text for c in group if c.text)
        merged_context = _merge_group_context(group, merged_byte_range)
        contextualized_text = text
        if first.contextualized_text != first.text:
            contextualized_text = format_contextualized_text(text, merged_context)

        out.append(
            Chunk(
                text=text,
                contextualized_text=contextualized_text,
                byte_range=merged_byte_range,
                line_range=LineRange(first.line_range.start, last.line_range.end),
                index=len(out),
                total_chunks=-1,
                context=merged_context,
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


def _merge_group_context(group: Sequence[Chunk], merged_range: ByteRange) -> ChunkContext:
    first_context = group[0].context

    merged_entities = _merge_entities(group, merged_range)
    merged_imports = _merge_imports(group)
    merged_siblings = _merge_siblings(group)
    merged_scope = _select_scope(group)
    merged_breadcrumb = _select_breadcrumb(group)
    merged_parse_errors = _merge_parse_errors(group)

    return replace(
        first_context,
        scope=merged_scope,
        breadcrumb=merged_breadcrumb,
        entities=merged_entities,
        siblings=merged_siblings,
        imports=merged_imports,
        parse_errors=merged_parse_errors,
    )


def _merge_entities(group: Sequence[Chunk], merged_range: ByteRange) -> list[EntityInfo]:
    out: list[EntityInfo] = []
    seen: set[tuple[str, str, int, int]] = set()

    for chunk in group:
        for entity in chunk.context.entities:
            br = entity.byte_range

            if br is not None:
                if br.end <= merged_range.start or br.start >= merged_range.end:
                    continue
                is_partial = br.start < merged_range.start or br.end > merged_range.end
                candidate = replace(entity, is_partial=is_partial)
                key = (entity.name, entity.type.value, br.start, br.end)
            else:
                candidate = entity
                key = (entity.name, entity.type.value, -1, -1)

            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)

    out.sort(key=lambda e: ((e.byte_range.start if e.byte_range else -1), e.name, e.type.value))
    return out


def _merge_imports(group: Sequence[Chunk]) -> list[ImportInfo]:
    out: list[ImportInfo] = []
    seen: set[tuple[str, str, bool, bool]] = set()

    for chunk in group:
        for item in chunk.context.imports:
            key = (item.name, item.source, item.is_default, item.is_namespace)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)

    return out


def _merge_siblings(group: Sequence[Chunk]) -> list[SiblingInfo]:
    out: list[SiblingInfo] = []
    seen: set[tuple[str, str, str, int, str]] = set()

    for chunk in group:
        for item in chunk.context.siblings:
            key = (item.name, item.type.value, item.position, item.distance, item.signature)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)

    return out


def _select_scope(group: Sequence[Chunk]) -> list[EntityInfo]:
    return max((chunk.context.scope for chunk in group), key=len, default=[])


def _select_breadcrumb(group: Sequence[Chunk]) -> list[str]:
    return max((chunk.context.breadcrumb for chunk in group), key=len, default=[])


def _merge_parse_errors(group: Sequence[Chunk]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    for chunk in group:
        for message in chunk.context.parse_errors:
            if message in seen:
                continue
            seen.add(message)
            out.append(message)

    return out
