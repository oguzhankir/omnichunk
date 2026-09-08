"""Translate segment-local chunk and entity coordinates to a canonical source."""

from __future__ import annotations

from dataclasses import replace

from omnichunk.types import ByteRange, Chunk, ChunkContext, EntityInfo, LineRange
from omnichunk.util.text_index import TextIndex


def rebase_context(context: ChunkContext, source: TextIndex, byte_offset: int) -> ChunkContext:
    """Rebase documented entity/scope ranges in O(number of attached entities)."""
    line_offset = source.line_for_byte(byte_offset)

    def translate(entity: EntityInfo) -> EntityInfo:
        br = entity.byte_range
        lr = entity.line_range
        if br is not None:
            br = ByteRange(byte_offset + br.start, byte_offset + br.end)
            if lr is not None:
                lr = LineRange(
                    source.line_for_byte(br.start),
                    source.line_for_byte(max(br.start, br.end - 1)),
                )
        elif lr is not None:
            lr = LineRange(line_offset + lr.start, line_offset + lr.end)
        return replace(entity, byte_range=br, line_range=lr)

    return replace(
        context,
        entities=[translate(entity) for entity in context.entities],
        scope=[translate(entity) for entity in context.scope],
    )


def rebase_chunk(chunk: Chunk, source: TextIndex, byte_offset: int) -> Chunk:
    """Preserve chunk data while moving all declared coordinates to ``source``."""
    start = byte_offset + chunk.byte_range.start
    end = byte_offset + chunk.byte_range.end
    return replace(
        chunk,
        byte_range=ByteRange(start, end),
        line_range=LineRange(
            source.line_for_byte(start), source.line_for_byte(max(start, end - 1))
        ),
        context=rebase_context(chunk.context, source, byte_offset),
    )
