from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import cast

from omnichunk.context.rebase import rebase_chunk
from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.formats.types import LoadedDocument
from omnichunk.sizing.nws import preprocess_nws_cumsum, slice_nws_cumsum
from omnichunk.types import Chunk, ChunkingError, ChunkOptions, ContentType, Language
from omnichunk.util.text_index import TextIndex

_CODE_ENGINE = CodeEngine()
_PROSE_ENGINE = ProseEngine()


def chunk_loaded_document(
    filepath: str,
    loaded: LoadedDocument,
    options: ChunkOptions,
) -> list[Chunk]:
    """Chunk canonical loader text with the same public source and budget contracts."""
    from omnichunk.config import validate_options
    from omnichunk.finalize import finalize_chunks, source_descriptor

    validate_options(options)
    index = TextIndex(loaded.text)
    source = source_descriptor(
        filepath,
        index,
        options,
        format_name=loaded.format_name,
        metadata={"warnings": list(loaded.warnings)},
    )
    engine_options = replace(options, overlap=None, overlap_lines=0)
    candidates = _iter_loaded_chunks(filepath, loaded, engine_options)
    chunks = list(
        finalize_chunks(filepath, loaded.text, candidates, options, index=index, source=source)
    )
    return _finalize_chunk_indexes(chunks)


def _iter_loaded_chunks(
    filepath: str,
    loaded: LoadedDocument,
    options: ChunkOptions,
) -> Iterator[Chunk]:
    content = loaded.text
    if not content.strip():
        if loaded.warnings:
            raise ChunkingError(f"{loaded.format_name} loader: {'; '.join(loaded.warnings)}")
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

        if segment.kind == "code":
            lang_raw = segment.metadata.get("language")
            segment_language = (
                cast(Language, lang_raw) if isinstance(lang_raw, str) else "plaintext"
            )
        else:
            lang_raw = segment.metadata.get("language")
            if isinstance(lang_raw, str):
                segment_language = cast(Language, lang_raw)
            else:
                segment_language = base_lang or "plaintext"

        if segment.char_start == 0 and segment.char_end == len(content):
            segment_index = text_index
            segment_cumsum = cumsum
        else:
            bs = text_index.byte_offset_for_char(segment.char_start)
            be = text_index.byte_offset_for_char(segment.char_end)
            segment_cumsum = slice_nws_cumsum(cumsum, bs, be)
            segment_index = TextIndex.from_parent_slice(
                text_index,
                segment.char_start,
                segment.char_end,
            )

        sub_options = replace(
            options,
            content_type=ContentType.CODE if segment.kind == "code" else ContentType.PROSE,
            language=segment_language,
            _precomputed_text_index=segment_index,
            _precomputed_nws_cumsum=segment_cumsum,
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
                parse_errors=list(
                    dict.fromkeys(
                        [
                            *rebased.context.parse_errors,
                            *(
                                f"{loaded.format_name} loader: {warning}"
                                for warning in loaded.warnings
                            ),
                        ]
                    )
                ),
                format_metadata={
                    **rebased.context.format_metadata,
                    **meta,
                    "source_format": loaded.format_name,
                },
            )
            yield replace(
                rebased,
                index=chunk_index,
                total_chunks=-1,
                context=merged_ctx,
            )
            chunk_index += 1


def _rebase_chunk(text_index: TextIndex, segment_char_start: int, chunk: Chunk) -> Chunk:
    return rebase_chunk(chunk, text_index, text_index.byte_offset_for_char(segment_char_start))


def _finalize_chunk_indexes(chunks: list[Chunk]) -> list[Chunk]:
    total = len(chunks)
    return [replace(chunk, index=idx, total_chunks=total) for idx, chunk in enumerate(chunks)]
