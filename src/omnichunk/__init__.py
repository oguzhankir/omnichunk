"""Structure-aware chunking; :class:`Chunker` adds ``achunk``, ``astream``, and ``abatch``."""

from . import plugins
from .budget import BudgetResult, TokenBudgetOptimizer
from .chunker import Chunker, chunk, chunk_directory, chunk_file, hierarchical_chunk
from .diff import chunk_diff
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
    stable_chunk_id,
)
from .types import (
    BatchResult,
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkDiff,
    ChunkNode,
    ChunkOptions,
    ChunkQualityScore,
    ChunkStats,
    ChunkTree,
    ContentType,
    EntityInfo,
    EntityType,
    ImportInfo,
    LineRange,
    SiblingInfo,
)

__version__ = "0.8.0"

__all__ = [
    "BatchResult",
    "BudgetResult",
    "ByteRange",
    "Chunk",
    "ChunkContext",
    "ChunkDiff",
    "ChunkEdge",
    "ChunkGraph",
    "ChunkNode",
    "ChunkOptions",
    "ChunkQualityScore",
    "ChunkStats",
    "ChunkTree",
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
    "TokenBudgetOptimizer",
    "__version__",
    "build_chunk_graph",
    "build_tfidf_matrix",
    "chunk",
    "chunk_diff",
    "chunk_directory",
    "chunk_file",
    "detect_semantic_boundaries",
    "detect_topic_shifts",
    "hierarchical_chunk",
    "split_sentences",
    "stable_chunk_id",
    "chunks_to_pinecone_vectors",
    "chunks_to_supabase_rows",
    "chunks_to_weaviate_objects",
    "list_registered_formatters",
    "list_registered_parsers",
    "plugins",
    "register_formatter",
    "register_parser",
]
