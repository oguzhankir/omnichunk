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


@dataclass(frozen=True)
class BatchResult:
    filepath: str
    chunks: list[Chunk] = field(default_factory=list)
    error: str | None = None
