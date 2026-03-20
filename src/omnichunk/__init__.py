"""Structure-aware chunking; :class:`Chunker` adds ``achunk``, ``astream``, and ``abatch``."""

from . import plugins
from .chunker import Chunker, chunk, chunk_directory, chunk_file
from .graph import ChunkEdge, ChunkGraph, EntityNode, build_chunk_graph
from .plugins import (
    list_registered_formatters,
    list_registered_parsers,
    register_formatter,
    register_parser,
)
from .semantic import (
    SemanticBoundaryResult,
    SemanticSplitter,
    build_tfidf_matrix,
    detect_semantic_boundaries,
    detect_topic_shifts,
    split_sentences,
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

__version__ = "0.7.0"

__all__ = [
    "BatchResult",
    "ByteRange",
    "Chunk",
    "ChunkContext",
    "ChunkEdge",
    "ChunkGraph",
    "ChunkOptions",
    "ChunkQualityScore",
    "ChunkStats",
    "Chunker",
    "ContentType",
    "EntityInfo",
    "EntityNode",
    "EntityType",
    "ImportInfo",
    "LineRange",
    "SemanticBoundaryResult",
    "SemanticSplitter",
    "SiblingInfo",
    "__version__",
    "build_chunk_graph",
    "build_tfidf_matrix",
    "chunk",
    "chunk_directory",
    "chunk_file",
    "detect_semantic_boundaries",
    "detect_topic_shifts",
    "split_sentences",
    "chunks_to_pinecone_vectors",
    "chunks_to_supabase_rows",
    "chunks_to_weaviate_objects",
    "list_registered_formatters",
    "list_registered_parsers",
    "plugins",
    "register_formatter",
    "register_parser",
]
