from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.hybrid_engine import HybridEngine
from omnichunk.engine.markup_engine import MarkupEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.sizing.nws import preprocess_nws_cumsum
from omnichunk.types import Chunk, ChunkOptions, ContentType
from omnichunk.util.detect import detect_content_type, detect_language
from omnichunk.util.text_index import TextIndex

_CODE_ENGINE = CodeEngine()
_PROSE_ENGINE = ProseEngine()
_MARKUP_ENGINE = MarkupEngine()
_HYBRID_ENGINE = HybridEngine()


def route_content(
    filepath: str, content: str, options: ChunkOptions
) -> tuple[ContentType, list[Chunk]]:
    language = options.language or detect_language(filepath=filepath, content=content)
    content_type = options.content_type or detect_content_type(
        filepath=filepath,
        content=content,
        language=language,
    )

    precomputed_text_index = options._precomputed_text_index
    if precomputed_text_index is None:
        precomputed_text_index = TextIndex(content)

    precomputed_nws_cumsum = options._precomputed_nws_cumsum
    if precomputed_nws_cumsum is None:
        precomputed_nws_cumsum = preprocess_nws_cumsum(content)

    effective_options = replace(
        options,
        filepath=filepath,
        language=language,
        content_type=content_type,
        _precomputed_text_index=precomputed_text_index,
        _precomputed_nws_cumsum=precomputed_nws_cumsum,
    )

    if content_type == ContentType.CODE:
        return content_type, _CODE_ENGINE.chunk(filepath, content, effective_options)
    if content_type == ContentType.MARKUP:
        return content_type, _MARKUP_ENGINE.chunk(filepath, content, effective_options)
    if content_type == ContentType.HYBRID:
        return content_type, _HYBRID_ENGINE.chunk(filepath, content, effective_options)
    return content_type, _PROSE_ENGINE.chunk(filepath, content, effective_options)


def route_content_stream(
    filepath: str,
    content: str,
    options: ChunkOptions,
) -> tuple[ContentType, Iterator[Chunk]]:
    language = options.language or detect_language(filepath=filepath, content=content)
    content_type = options.content_type or detect_content_type(
        filepath=filepath,
        content=content,
        language=language,
    )

    precomputed_text_index = options._precomputed_text_index
    if precomputed_text_index is None:
        precomputed_text_index = TextIndex(content)

    precomputed_nws_cumsum = options._precomputed_nws_cumsum
    if precomputed_nws_cumsum is None:
        precomputed_nws_cumsum = preprocess_nws_cumsum(content)

    effective_options = replace(
        options,
        filepath=filepath,
        language=language,
        content_type=content_type,
        _precomputed_text_index=precomputed_text_index,
        _precomputed_nws_cumsum=precomputed_nws_cumsum,
    )

    if content_type == ContentType.CODE:
        return content_type, _CODE_ENGINE.stream(filepath, content, effective_options)
    if content_type == ContentType.MARKUP:
        return content_type, _MARKUP_ENGINE.stream(filepath, content, effective_options)
    if content_type == ContentType.HYBRID:
        return content_type, _HYBRID_ENGINE.stream(filepath, content, effective_options)
    return content_type, _PROSE_ENGINE.stream(filepath, content, effective_options)
