"""Typed component contracts used by the shared chunking pipeline."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Protocol

from omnichunk.formats.types import LoadedDocument
from omnichunk.types import ByteRange, Chunk, ChunkContext, ChunkOptions


class SizeCounter(Protocol):
    def __call__(self, text: str, /) -> int: ...


class DocumentLoader(Protocol):
    def __call__(self, source: bytes, /) -> LoadedDocument: ...


class StructureParser(Protocol):
    def __call__(self, filepath: str, content: str, /) -> Any: ...


class BoundaryPolicy(Protocol):
    def __call__(self, text: str, /) -> Iterable[ByteRange]: ...


class ContextRenderer(Protocol):
    def __call__(self, text: str, context: ChunkContext, overlap_text: str = "") -> str: ...


class ChunkExporter(Protocol):
    def __call__(self, chunks: Sequence[Chunk], /) -> str: ...


class ChunkingEngine(Protocol):
    """Engines propose canonical source spans; finalization validates output."""

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]: ...
