from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from omnichunk.sizing.counter import make_size_counter, make_token_counter
from omnichunk.sizing.nws import get_nws_count
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkOptions,
    ContentType,
    LineRange,
)
from omnichunk.util.detect import detect_language
from omnichunk.util.text_index import TextIndex

from .boundaries import detect_semantic_boundaries
from .sentences import split_sentences


@dataclass(frozen=True)
class SemanticSplitter:
    """Splits prose text into semantically coherent chunks.

    embed_fn must accept list[str] and return np.ndarray of shape (N, D).
    window: number of sentences per context window for boundary detection.
    threshold: cosine similarity below which a boundary is placed.
    min_chunk_sentences: minimum sentences per output chunk.
    sentence_splitter_fn: optional custom sentence splitter.
    """

    embed_fn: Callable[[list[str]], np.ndarray]
    window: int = 3
    threshold: float = 0.3
    min_chunk_sentences: int = 1
    sentence_splitter_fn: Callable[[str], list[str]] | None = None

    def split(
        self,
        filepath: str,
        text: str,
        options: ChunkOptions,
    ) -> list[Chunk]:
        if not text.strip():
            return []

        text_index = options._precomputed_text_index
        if text_index is None:
            text_index = TextIndex(text)
        cumsum = options._precomputed_nws_cumsum
        if cumsum is None:
            raise RuntimeError("SemanticSplitter requires precomputed NWS cumsum on options")

        language = options.language or detect_language(filepath=filepath, content=text)

        triples = split_sentences(text, splitter_fn=self.sentence_splitter_fn)
        sentence_texts = [t for t, _, _ in triples]
        if not sentence_texts:
            return []

        boundary_res = detect_semantic_boundaries(
            sentence_texts,
            embed_fn=self.embed_fn,
            window=self.window,
            threshold=self.threshold,
            min_chunk_sentences=max(1, self.min_chunk_sentences),
        )
        boundaries = list(boundary_res.boundary_indices)
        n = len(triples)

        starts = [0]
        for b in boundaries:
            starts.append(b + 1)
        ends = list(boundaries) + [n - 1]

        groups: list[tuple[int, int]] = []
        if len(starts) != len(ends):
            raise RuntimeError("semantic splitter: starts/ends length mismatch")
        for s, e in zip(starts, ends):
            if s <= e:
                groups.append((s, e))

        size_counter = make_size_counter(
            options.size_unit,
            options.tokenizer,
            max_token_chars=256,
            chunk_size=options.max_chunk_size,
        )
        token_counter = make_token_counter(
            options.tokenizer,
            max_token_chars=256,
            chunk_size=options.max_chunk_size,
        )

        def piece_size(sub: str) -> int:
            return int(size_counter(sub))

        def subdivide_sentence_indices(s: int, e: int) -> list[tuple[int, int]]:
            stack = [(s, e)]
            final: list[tuple[int, int]] = []
            while stack:
                a, b = stack.pop()
                chunk_str = "".join(triples[i][0] for i in range(a, b + 1))
                if piece_size(chunk_str) <= options.max_chunk_size:
                    final.append((a, b))
                    continue
                if a < b:
                    mid = (a + b + 1) // 2
                    stack.append((mid, b))
                    stack.append((a, mid - 1))
                    continue
                final.append((a, b))
            final.sort(key=lambda x: (x[0], x[1]))
            return final

        def char_piece_ranges(c0: int, c1: int) -> list[tuple[int, int]]:
            """Split [c0, c1) char range until each piece fits max_chunk_size."""
            stack = [(c0, c1)]
            parts: list[tuple[int, int]] = []
            while stack:
                a, b = stack.pop()
                if a >= b:
                    continue
                sub = text[a:b]
                if piece_size(sub) <= options.max_chunk_size:
                    parts.append((a, b))
                    continue
                if b - a <= 1:
                    parts.append((a, b))
                    continue
                mid = (a + b) // 2
                stack.append((mid, b))
                stack.append((a, mid))
            parts.sort(key=lambda x: (x[0], x[1]))
            return parts

        expanded_chars: list[tuple[int, int]] = []
        for s, e in groups:
            for a, b in subdivide_sentence_indices(s, e):
                chunk_str = "".join(triples[i][0] for i in range(a, b + 1))
                c0, c1 = triples[a][1], triples[b][2]
                if piece_size(chunk_str) <= options.max_chunk_size:
                    expanded_chars.append((c0, c1))
                else:
                    expanded_chars.extend(char_piece_ranges(c0, c1))

        chunks: list[Chunk] = []
        for idx, (c_start, c_end) in enumerate(expanded_chars):
            chunk_text = text[c_start:c_end]
            if not chunk_text.strip():
                continue
            byte_start = text_index.byte_offset_for_char(c_start)
            byte_end = text_index.byte_offset_for_char(c_end)
            line_start = text_index.line_for_char(c_start)
            line_end = text_index.line_for_char(max(c_start, c_end - 1))

            context = ChunkContext(
                filepath=filepath,
                language=language,
                content_type=ContentType.PROSE,
            )
            chunks.append(
                Chunk(
                    text=chunk_text,
                    contextualized_text=chunk_text,
                    byte_range=ByteRange(byte_start, byte_end),
                    line_range=LineRange(line_start, max(line_start, line_end)),
                    index=idx,
                    total_chunks=-1,
                    context=context,
                    token_count=int(token_counter(chunk_text)),
                    char_count=len(chunk_text),
                    nws_count=get_nws_count(cumsum, byte_start, byte_end),
                )
            )

        total = len(chunks)
        return [
            Chunk(
                text=c.text,
                contextualized_text=c.contextualized_text,
                byte_range=c.byte_range,
                line_range=c.line_range,
                index=i,
                total_chunks=total,
                context=c.context,
                token_count=c.token_count,
                char_count=c.char_count,
                nws_count=c.nws_count,
            )
            for i, c in enumerate(chunks)
        ]
