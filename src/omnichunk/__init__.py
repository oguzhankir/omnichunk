"""Structure-aware chunking; :class:`Chunker` adds ``achunk``, ``astream``, and ``abatch``."""

from . import plugins
from .budget import BudgetResult, TokenBudgetOptimizer
from .chunker import Chunker, chunk, chunk_directory, chunk_file, hierarchical_chunk
from .dedup import dedup_chunks
from .diff import chunk_diff
from .eval import ChunkEvalScores, EvalReport, eval_report_to_dict, evaluate_chunks
from .formats import (
    FormatSegment,
    LoadedDocument,
    chunk_loaded_document,
    load_docx_bytes,
    load_ipynb,
    load_latex,
    load_pdf_bytes,
)
from .graph import ChunkEdge, ChunkGraph, EntityNode, build_chunk_graph
from .otel import maybe_span
from .plugins import (
    list_registered_formatters,
    list_registered_parsers,
    register_formatter,
    register_parser,
)
from .propositions import Proposition
from .semantic import (
    SemanticBoundaryResult,
    SemanticSplitter,
    build_tfidf_matrix,
    detect_semantic_boundaries,
    detect_topic_shifts,
    split_sentences,
)
from .serialization import (
    chunk_from_dict,
    chunks_to_pinecone_vectors,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
    stable_chunk_id,
)
from .store import ChunkStore, SyncResult
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
    UpsertBatch,
)

__version__ = "0.10.1"

__all__ = [
    "BatchResult",
    "BudgetResult",
    "ByteRange",
    "Chunk",
    "ChunkContext",
    "ChunkEvalScores",
    "ChunkDiff",
    "ChunkEdge",
    "ChunkGraph",
    "ChunkNode",
    "ChunkOptions",
    "ChunkQualityScore",
    "ChunkStats",
    "ChunkTree",
    "ChunkStore",
    "Chunker",
    "ContentType",
    "EvalReport",
    "FormatSegment",
    "LoadedDocument",
    "EntityInfo",
    "EntityNode",
    "EntityType",
    "ImportInfo",
    "LineRange",
    "Proposition",
    "SemanticBoundaryResult",
    "SemanticSplitter",
    "SiblingInfo",
    "SyncResult",
    "TokenBudgetOptimizer",
    "UpsertBatch",
    "__version__",
    "build_chunk_graph",
    "build_tfidf_matrix",
    "chunk",
    "chunk_diff",
    "chunk_from_dict",
    "chunk_loaded_document",
    "dedup_chunks",
    "evaluate_chunks",
    "eval_report_to_dict",
    "chunk_directory",
    "chunk_file",
    "detect_semantic_boundaries",
    "detect_topic_shifts",
    "hierarchical_chunk",
    "load_docx_bytes",
    "load_ipynb",
    "load_latex",
    "load_pdf_bytes",
    "split_sentences",
    "stable_chunk_id",
    "maybe_span",
    "chunks_to_pinecone_vectors",
    "chunks_to_supabase_rows",
    "chunks_to_weaviate_objects",
    "list_registered_formatters",
    "list_registered_parsers",
    "plugins",
    "register_formatter",
    "register_parser",
]
