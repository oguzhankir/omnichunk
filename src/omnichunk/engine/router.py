from __future__ import annotations

from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.hybrid_engine import HybridEngine
from omnichunk.engine.markup_engine import MarkupEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.types import Chunk, ChunkOptions, ContentType
from omnichunk.util.detect import detect_content_type, detect_language


_CODE_ENGINE = CodeEngine()
_PROSE_ENGINE = ProseEngine()
_MARKUP_ENGINE = MarkupEngine()
_HYBRID_ENGINE = HybridEngine()


def route_content(filepath: str, content: str, options: ChunkOptions) -> tuple[ContentType, list[Chunk]]:
    language = options.language or detect_language(filepath=filepath, content=content)
    content_type = options.content_type or detect_content_type(
        filepath=filepath,
        content=content,
        language=language,
    )

    options.filepath = filepath
    options.language = language
    options.content_type = content_type

    if content_type == ContentType.CODE:
        return content_type, _CODE_ENGINE.chunk(filepath, content, options)
    if content_type == ContentType.MARKUP:
        return content_type, _MARKUP_ENGINE.chunk(filepath, content, options)
    if content_type == ContentType.HYBRID:
        return content_type, _HYBRID_ENGINE.chunk(filepath, content, options)
    return content_type, _PROSE_ENGINE.chunk(filepath, content, options)
