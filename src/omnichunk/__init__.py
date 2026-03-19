"""Structure-aware chunking; :class:`Chunker` adds ``achunk``, ``astream``, and ``abatch``."""

from .chunker import Chunker, chunk, chunk_directory, chunk_file
from .types import (
    BatchResult,
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkOptions,
    ChunkQualityScore,
    ChunkStats,
    ContentType,
    EntityInfo,
    EntityType,
    ImportInfo,
    LineRange,
    SiblingInfo,
)

__version__ = "0.5.0"

__all__ = [
    "BatchResult",
    "ByteRange",
    "Chunk",
    "ChunkContext",
    "ChunkOptions",
    "ChunkQualityScore",
    "ChunkStats",
    "Chunker",
    "ContentType",
    "EntityInfo",
    "EntityType",
    "ImportInfo",
    "LineRange",
    "SiblingInfo",
    "__version__",
    "chunk",
    "chunk_directory",
    "chunk_file",
]
