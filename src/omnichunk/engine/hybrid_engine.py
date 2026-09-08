from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace

from omnichunk.context.rebase import rebase_chunk
from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.sizing.nws import preprocess_nws_cumsum, slice_nws_cumsum
from omnichunk.types import Chunk, ChunkOptions, ContentType
from omnichunk.util.text_index import TextIndex


class HybridEngine:
    def __init__(self) -> None:
        self._code_engine = CodeEngine()
        self._prose_engine = ProseEngine()

    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        chunks = list(self._iter_chunks(filepath, content, options))
        return _finalize_chunk_indexes(chunks)

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        for idx, chunk in enumerate(self._iter_chunks(filepath, content, options)):
            yield _with_unknown_total(chunk, idx)

    def _iter_chunks(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        if not content.strip():
            return

        precomputed_text_index = options._precomputed_text_index
        if isinstance(precomputed_text_index, TextIndex):
            text_index = precomputed_text_index
        else:
            text_index = TextIndex(content)

        segments = _split_hybrid_segments(content)
        chunk_index = 0

        for segment in segments:
            segment_start, segment_end, segment_kind = segment
            segment_text = content[segment_start:segment_end]
            if not segment_text.strip():
                continue

            if segment_start == 0 and segment_end == len(content):
                segment_index = text_index
                segment_cumsum = options._precomputed_nws_cumsum
            else:
                bs = text_index.byte_offset_for_char(segment_start)
                be = text_index.byte_offset_for_char(segment_end)
                pc = options._precomputed_nws_cumsum
                if pc is not None:
                    segment_cumsum = slice_nws_cumsum(pc, bs, be)
                else:
                    segment_cumsum = preprocess_nws_cumsum(
                        segment_text,
                        backend=options.nws_backend,
                    )
                segment_index = TextIndex.from_parent_slice(
                    text_index,
                    segment_start,
                    segment_end,
                )

            sub_options = replace(
                options,
                content_type=ContentType.CODE if segment_kind == "code" else ContentType.PROSE,
                _precomputed_text_index=segment_index,
                _precomputed_nws_cumsum=segment_cumsum,
            )
            if segment_kind == "code":
                local_chunks = self._code_engine.stream(filepath, segment_text, sub_options)
            else:
                local_chunks = self._prose_engine.stream(filepath, segment_text, sub_options)

            for local_chunk in local_chunks:
                rebased = _rebase_chunk(text_index, segment_start, local_chunk)
                yield replace(
                    rebased,
                    index=chunk_index,
                    total_chunks=-1,
                )
                chunk_index += 1


def _split_hybrid_segments(content: str) -> list[tuple[int, int, str]]:
    if "# %%" in content:
        return _split_by_cells(content)

    docstring_matches = list(re.finditer(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', content))
    doc_chars = sum(m.end() - m.start() for m in docstring_matches)
    if doc_chars / max(1, len(content)) <= 0.4:
        return [(0, len(content), "code")]

    segments: list[tuple[int, int, str]] = []
    cursor = 0
    for match in docstring_matches:
        if match.start() > cursor:
            segments.append((cursor, match.start(), "code"))
        segments.append((match.start(), match.end(), "prose"))
        cursor = match.end()
    if cursor < len(content):
        segments.append((cursor, len(content), "code"))
    return segments


def _split_by_cells(content: str) -> list[tuple[int, int, str]]:
    boundaries = [m.start() for m in re.finditer(r"(?m)^#\s*%%", content)]
    if not boundaries:
        return [(0, len(content), "code")]

    boundaries = [0] + boundaries + [len(content)]
    segments: list[tuple[int, int, str]] = []
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        text = content[start:end]
        segment_type = "prose" if _looks_markdown_cell(text) else "code"
        segments.append((start, end, segment_type))
    return segments


def _looks_markdown_cell(text: str) -> bool:
    if "# %% [markdown]" in text.lower():
        return True
    stripped = text.strip()
    return stripped.startswith('"""') or stripped.startswith("'''")


def _rebase_chunk(text_index: TextIndex, segment_char_start: int, chunk: Chunk) -> Chunk:
    return rebase_chunk(chunk, text_index, text_index.byte_offset_for_char(segment_char_start))


def _finalize_chunk_indexes(chunks: list[Chunk]) -> list[Chunk]:
    total = len(chunks)
    return [replace(chunk, index=idx, total_chunks=total) for idx, chunk in enumerate(chunks)]


def _with_unknown_total(chunk: Chunk, index: int) -> Chunk:
    return replace(chunk, index=index, total_chunks=-1)
