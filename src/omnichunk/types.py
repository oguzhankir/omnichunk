from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class ContentType(Enum):
    CODE = "code"
    PROSE = "prose"
    MARKUP = "markup"
    HYBRID = "hybrid"


class EntityType(Enum):
    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    IMPORT = "import"
    EXPORT = "export"
    MODULE = "module"
    DECORATOR = "decorator"
    CONSTANT = "constant"
    HEADING = "heading"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    CODE_BLOCK = "code_block"
    FRONTMATTER = "frontmatter"


Language = Literal[
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "c",
    "cpp",
    "csharp",
    "ruby",
    "php",
    "swift",
    "kotlin",
    "scala",
    "haskell",
    "lua",
    "zig",
    "elixir",
    "markdown",
    "html",
    "xml",
    "yaml",
    "json",
    "toml",
    "plaintext",
]


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int


@dataclass(frozen=True)
class LineRange:
    start: int
    end: int


@dataclass(frozen=True)
class EntityInfo:
    """An entity detected within source content."""

    name: str
    type: EntityType
    signature: str = ""
    docstring: str | None = None
    byte_range: ByteRange | None = None
    line_range: LineRange | None = None
    is_partial: bool = False
    parent: str | None = None


@dataclass(frozen=True)
class SiblingInfo:
    """A sibling entity near the current chunk."""

    name: str
    type: EntityType
    position: Literal["before", "after"]
    distance: int
    signature: str = ""


@dataclass(frozen=True)
class ImportInfo:
    """An import dependency."""

    name: str
    source: str
    is_default: bool = False
    is_namespace: bool = False


@dataclass(frozen=True)
class ChunkContext:
    """Rich contextual metadata for a chunk."""

    filepath: str = ""
    language: Language = "plaintext"
    content_type: ContentType = ContentType.PROSE

    scope: list[EntityInfo] = field(default_factory=list)
    breadcrumb: list[str] = field(default_factory=list)
    entities: list[EntityInfo] = field(default_factory=list)
    siblings: list[SiblingInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)

    heading_hierarchy: list[str] = field(default_factory=list)
    section_type: str = ""
    parse_errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Chunk:
    """A single chunk with full context."""

    text: str
    contextualized_text: str

    byte_range: ByteRange
    line_range: LineRange
    index: int
    total_chunks: int

    context: ChunkContext

    token_count: int = 0
    char_count: int = 0
    nws_count: int = 0


@dataclass(frozen=True)
class ChunkNode:
    """A single node in a ChunkTree — wraps a Chunk with parent/child links."""

    chunk: Chunk
    level: int
    """0 = finest granularity (leaves), max_level = coarsest (roots)."""
    parent_index: int | None
    """Index into ChunkTree.nodes of this node's parent, or None if root."""
    child_indices: tuple[int, ...]
    """Sorted indices into ChunkTree.nodes of this node's children."""


@dataclass
class ChunkTree:
    """Multi-level chunk hierarchy produced by hierarchical_chunk()."""

    nodes: list[ChunkNode]
    level_count: int

    def leaves(self) -> list[Chunk]:
        """Return all level-0 chunks in source order."""
        return [n.chunk for n in self.nodes if n.level == 0]

    def roots(self) -> list[Chunk]:
        """Return all top-level (coarsest) chunks in source order."""
        max_level = self.level_count - 1
        return [n.chunk for n in self.nodes if n.level == max_level]

    def at_level(self, level: int) -> list[Chunk]:
        """Return all chunks at a given level in source order."""
        if level < 0 or level >= self.level_count:
            raise ValueError(f"level must be in [0, {self.level_count - 1}]")
        return [n.chunk for n in self.nodes if n.level == level]

    def parent(self, chunk: Chunk) -> Chunk | None:
        """Return the parent chunk of the given chunk, or None if root."""
        for node in self.nodes:
            if node.chunk is chunk and node.parent_index is not None:
                return self.nodes[node.parent_index].chunk
        return None

    def children(self, chunk: Chunk) -> list[Chunk]:
        """Return the children of the given chunk, in source order."""
        for node in self.nodes:
            if node.chunk is chunk:
                ordered = sorted(
                    node.child_indices,
                    key=lambda i: self.nodes[i].chunk.byte_range.start,
                )
                return [self.nodes[i].chunk for i in ordered]
        return []

    def to_flat_list(self, level: int | None = None) -> list[Chunk]:
        """Return all chunks at `level`, or all chunks if level is None."""
        if level is None:
            return [n.chunk for n in self.nodes]
        return self.at_level(level)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict for storage/transport."""
        from omnichunk.serialization import chunk_to_dict

        return {
            "level_count": self.level_count,
            "nodes": [
                {
                    "level": n.level,
                    "parent_index": n.parent_index,
                    "child_indices": list(n.child_indices),
                    "chunk": chunk_to_dict(n.chunk),
                }
                for n in self.nodes
            ],
        }


@dataclass(frozen=True)
class ChunkDiff:
    """Result of incremental re-chunking after a content change."""

    added: list[Chunk]
    removed_ids: list[str]
    unchanged: list[Chunk]

    @property
    def total_added(self) -> int:
        return len(self.added)

    @property
    def total_removed(self) -> int:
        return len(self.removed_ids)

    @property
    def total_unchanged(self) -> int:
        return len(self.unchanged)


@dataclass(frozen=True)
class ChunkQualityScore:
    """Quality metrics for a chunk."""

    index: int
    overall: float
    entity_integrity: float
    scope_consistency: float
    size_balance: float
    size_value: int


@dataclass(frozen=True)
class ChunkStats:
    """Aggregate statistics for a chunk set."""

    total_chunks: int
    average_size: float
    min_size: int
    max_size: int
    size_unit: Literal["tokens", "chars", "nws"]
    entity_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class ChunkOptions:
    """Configuration for chunking behavior."""

    max_chunk_size: int = 1500
    min_chunk_size: int = 50
    size_unit: Literal["tokens", "chars", "nws"] = "tokens"
    tokenizer: str | Callable[[str], int] | None = None
    nws_backend: Literal["auto", "python", "rust"] = "auto"

    context_mode: Literal["none", "minimal", "full"] = "full"
    sibling_detail: Literal["none", "names", "signatures"] = "signatures"
    max_siblings: int = 3
    include_imports: bool = True
    filter_imports: bool = False

    overlap: int | float | None = None
    overlap_lines: int = 0

    language: Language | None = None
    content_type: ContentType | None = None
    filepath: str = ""

    preserve_decorators: bool = True
    preserve_comments: bool = True
    include_header_in_sections: bool = True

    _precomputed_nws_cumsum: Any | None = None
    _precomputed_text_index: Any | None = None

    # Semantic chunking options
    semantic: bool = False
    semantic_embed_fn: object = None
    semantic_window: int = 3
    semantic_threshold: float = 0.3
    semantic_min_sentences: int = 1
    semantic_sentence_splitter: object = None


@dataclass(frozen=True)
class BatchResult:
    filepath: str
    chunks: list[Chunk] = field(default_factory=list)
    error: str | None = None
