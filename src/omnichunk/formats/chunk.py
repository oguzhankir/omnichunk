from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import numpy as np

from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.formats.types import LoadedDocument
from omnichunk.sizing.nws import preprocess_nws_cumsum
from omnichunk.types import ByteRange, Chunk, ChunkOptions, ContentType, LineRange
from omnichunk.util.text_index import TextIndex

_CODE_ENGINE = CodeEngine()
_PROSE_ENGINE = ProseEngine()


def chunk_loaded_document(
    filepath: str,
    loaded: LoadedDocument,
    options: ChunkOptions,
) -> list[Chunk]:
    """Chunk a loaded document by routing each segment to ProseEngine or CodeEngine."""
    chunks = list(_iter_loaded_chunks(filepath, loaded, options))
    return _finalize_chunk_indexes(chunks)


def _iter_loaded_chunks(
    filepath: str,
    loaded: LoadedDocument,
    options: ChunkOptions,
) -> Iterator[Chunk]:
    content = loaded.text
    if not content.strip():
        return

    text_index = TextIndex(content)
    cumsum = options._precomputed_nws_cumsum
    if cumsum is None:
        cumsum = preprocess_nws_cumsum(content, backend=options.nws_backend)

    base_lang = options.language
    chunk_index = 0

    for segment in loaded.segments:
        seg_text = content[segment.char_start : segment.char_end]
        if not seg_text.strip():
            continue

        sub_options = replace(options)
        if segment.kind == "code":
            sub_options.content_type = ContentType.CODE
            lang = segment.metadata.get("language")
            sub_options.language = lang if isinstance(lang, str) else "plaintext"
        else:
            sub_options.content_type = ContentType.PROSE
            lang = segment.metadata.get("language")
            sub_options.language = (
                lang if isinstance(lang, str) else (base_lang or "plaintext")
            )

        if segment.char_start == 0 and segment.char_end == len(content):
            sub_options._precomputed_text_index = text_index
            sub_options._precomputed_nws_cumsum = cumsum
        else:
            bs = text_index.byte_offset_for_char(segment.char_start)
            be = text_index.byte_offset_for_char(segment.char_end)
            pc = cumsum
            if isinstance(pc, np.ndarray) and int(pc.size) > be:
                sub_options._precomputed_nws_cumsum = pc[bs : be + 1] - pc[bs]
            else:
                sub_options._precomputed_nws_cumsum = preprocess_nws_cumsum(
                    seg_text,
                    backend=options.nws_backend,
                )
            sub_options._precomputed_text_index = TextIndex.from_parent_slice(
                text_index,
                segment.char_start,
                segment.char_end,
            )

        if segment.kind == "code":
            stream = _CODE_ENGINE.stream(filepath, seg_text, sub_options)
        else:
            stream = _PROSE_ENGINE.stream(filepath, seg_text, sub_options)

        meta = dict(segment.metadata)
        for local_chunk in stream:
            rebased = _rebase_chunk(text_index, segment.char_start, local_chunk)
            merged_ctx = replace(
                rebased.context,
                filepath=filepath,
                format_metadata={
                    **rebased.context.format_metadata,
                    **meta,
                    "source_format": loaded.format_name,
                },
            )
            yield Chunk(
                text=rebased.text,
                contextualized_text=rebased.contextualized_text,
                byte_range=rebased.byte_range,
                line_range=rebased.line_range,
                index=chunk_index,
                total_chunks=-1,
                context=merged_ctx,
                token_count=rebased.token_count,
                char_count=rebased.char_count,
                nws_count=rebased.nws_count,
            )
            chunk_index += 1


def _rebase_chunk(text_index: TextIndex, segment_char_start: int, chunk: Chunk) -> Chunk:
    segment_byte_start = text_index.byte_offset_for_char(segment_char_start)
    line_offset = text_index.line_for_char(segment_char_start)

    return Chunk(
        text=chunk.text,
        contextualized_text=chunk.contextualized_text,
        byte_range=ByteRange(
            start=segment_byte_start + chunk.byte_range.start,
            end=segment_byte_start + chunk.byte_range.end,
        ),
        line_range=LineRange(
            start=line_offset + chunk.line_range.start,
            end=line_offset + chunk.line_range.end,
        ),
        index=chunk.index,
        total_chunks=chunk.total_chunks,
        context=chunk.context,
        token_count=chunk.token_count,
        char_count=chunk.char_count,
        nws_count=chunk.nws_count,
    )


def _finalize_chunk_indexes(chunks: list[Chunk]) -> list[Chunk]:
    total = len(chunks)
    return [
        Chunk(
            text=chunk.text,
            contextualized_text=chunk.contextualized_text,
            byte_range=chunk.byte_range,
            line_range=chunk.line_range,
            index=idx,
            total_chunks=total,
            context=chunk.context,
            token_count=chunk.token_count,
            char_count=chunk.char_count,
            nws_count=chunk.nws_count,
        )
        for idx, chunk in enumerate(chunks)
    ]
