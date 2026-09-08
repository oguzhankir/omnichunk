from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any

from numpy.typing import NDArray

from omnichunk.config import validate_options
from omnichunk.finalize import finalize_chunks
from omnichunk.types import ByteRange, Chunk, ChunkContext, ChunkOptions, ContentType, LineRange
from omnichunk.util.detect import detect_language
from omnichunk.util.text_index import TextIndex

from .boundaries import detect_semantic_boundaries
from .sentences import split_sentences


@dataclass(frozen=True)
class SemanticSplitter:
    """Propose semantic boundaries and finalize source spans using shared policies.

    ``embed_fn`` returns a floating array with one row per input. ``window`` is
    the number of sentences in an embedding window, ``threshold`` controls low
    similarities, and ``min_chunk_sentences`` constrains semantic boundaries.
    The size budget can force a further split within a semantic group.
    """

    embed_fn: Callable[[list[str]], NDArray[Any]]
    window: int = 3
    threshold: float = 0.3
    min_chunk_sentences: int = 1
    sentence_splitter_fn: Callable[[str], list[str]] | None = None

    def split(self, filepath: str, text: str, options: ChunkOptions) -> list[Chunk]:
        """Return final chunks without requiring any private precomputed indices."""
        from omnichunk.engine.semantic_engine import _validated_embed_fn

        effective = replace(
            options,
            filepath=filepath,
            semantic=True,
            semantic_embed_fn=self.embed_fn,
            semantic_window=self.window,
            semantic_threshold=self.threshold,
            semantic_min_sentences=self.min_chunk_sentences,
            semantic_sentence_splitter=self.sentence_splitter_fn,
        )
        validate_options(effective)
        index = TextIndex(text)
        effective = replace(effective, _precomputed_text_index=index)
        validated = replace(self, embed_fn=_validated_embed_fn(self.embed_fn))
        chunks = list(
            finalize_chunks(
                filepath,
                text,
                validated._candidates(filepath, text, effective),
                effective,
                index=index,
            )
        )
        return [replace(chunk, total_chunks=len(chunks)) for chunk in chunks]

    def _candidates(self, filepath: str, text: str, options: ChunkOptions) -> Iterator[Chunk]:
        """Internal engine input: source spans only; no duplicate budget enforcement."""
        if not text.strip():
            return
        index = options._precomputed_text_index or TextIndex(text)
        language = options.language or detect_language(filepath=filepath, content=text)
        sentences = split_sentences(text, splitter_fn=self.sentence_splitter_fn)
        if not sentences:
            return
        boundaries = detect_semantic_boundaries(
            [sentence for sentence, _, _ in sentences],
            embed_fn=self.embed_fn,
            window=self.window,
            threshold=self.threshold,
            min_chunk_sentences=self.min_chunk_sentences,
        ).boundary_indices
        start_sentence = 0
        for position, end_sentence in enumerate((*boundaries, len(sentences) - 1)):
            start = sentences[start_sentence][1]
            end = sentences[end_sentence][2]
            byte_start = index.byte_offset_for_char(start)
            byte_end = index.byte_offset_for_char(end)
            chunk_text = text[start:end]
            yield Chunk(
                text=chunk_text,
                contextualized_text=chunk_text,
                byte_range=ByteRange(byte_start, byte_end),
                line_range=LineRange(
                    index.line_for_char(start), index.line_for_char(max(start, end - 1))
                ),
                index=position,
                total_chunks=-1,
                context=ChunkContext(
                    filepath=filepath, language=language, content_type=ContentType.PROSE
                ),
            )
            start_sentence = end_sentence + 1
