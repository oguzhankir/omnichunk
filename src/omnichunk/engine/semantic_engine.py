from __future__ import annotations

from collections.abc import Iterator

from omnichunk.semantic.splitter import SemanticSplitter
from omnichunk.types import Chunk, ChunkOptions


class SemanticEngine:
    """Engine for embedding-based semantic chunking of prose content."""

    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        splitter = self._build_splitter(options)
        return splitter.split(filepath, content, options)

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        chunks = self.chunk(filepath, content, options)
        for idx, ch in enumerate(chunks):
            yield _with_unknown_total(ch, idx)

    def _build_splitter(self, options: ChunkOptions) -> SemanticSplitter:
        embed_fn = options.semantic_embed_fn
        if embed_fn is None or not callable(embed_fn):
            raise ValueError(
                "semantic=True requires semantic_embed_fn: "
                "Callable[[list[str]], np.ndarray]"
            )
        ss = options.semantic_sentence_splitter
        sentence_fn = ss if callable(ss) else None
        return SemanticSplitter(
            embed_fn=embed_fn,
            window=int(options.semantic_window),
            threshold=float(options.semantic_threshold),
            min_chunk_sentences=max(1, int(options.semantic_min_sentences)),
            sentence_splitter_fn=sentence_fn,
        )


def _with_unknown_total(chunk: Chunk, index: int) -> Chunk:
    return Chunk(
        text=chunk.text,
        contextualized_text=chunk.contextualized_text,
        byte_range=chunk.byte_range,
        line_range=chunk.line_range,
        index=index,
        total_chunks=-1,
        context=chunk.context,
        token_count=chunk.token_count,
        char_count=chunk.char_count,
        nws_count=chunk.nws_count,
    )
