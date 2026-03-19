"""Structure-aware chunking; :class:`Chunker` adds ``achunk``, ``astream``, and ``abatch``."""

from . import plugins
from .chunker import Chunker, chunk, chunk_directory, chunk_file
from .plugins import (
    list_registered_formatters,
    list_registered_parsers,
    register_formatter,
    register_parser,
)
from .serialization import (
    chunks_to_pinecone_vectors,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
)
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

__version__ = "0.6.0"

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
    "chunks_to_pinecone_vectors",
    "chunks_to_supabase_rows",
    "chunks_to_weaviate_objects",
    "list_registered_formatters",
    "list_registered_parsers",
    "plugins",
    "register_formatter",
    "register_parser",
]
