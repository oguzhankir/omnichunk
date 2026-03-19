from __future__ import annotations

from dataclasses import replace
import re

from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.prose_engine import ProseEngine
from omnichunk.types import ByteRange, Chunk, ChunkOptions, ContentType, LineRange


class HybridEngine:
    def __init__(self) -> None:
        self._code_engine = CodeEngine()
        self._prose_engine = ProseEngine()

    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        if not content.strip():
            return []

        segments = _split_hybrid_segments(content)
        chunks: list[Chunk] = []

        for segment in segments:
            segment_text = content[segment[0] : segment[1]]
            if not segment_text.strip():
                continue

            sub_options = replace(options)
            sub_options.content_type = ContentType.CODE if segment[2] == "code" else ContentType.PROSE

            if segment[2] == "code":
                local_chunks = self._code_engine.chunk(filepath, segment_text, sub_options)
            else:
                local_chunks = self._prose_engine.chunk(filepath, segment_text, sub_options)

            rebased = _rebase_chunks(content, segment[0], local_chunks)
            chunks.extend(rebased)

        total = len(chunks)
        return [
            Chunk(
                text=chunk.text,
                contextualized_text=chunk.contextualized_text,
                byte_range=chunk.byte_range,
                line_range=chunk.line_range,
                index=idx,
                total_chunks=total,
                context=chunk.context,
                token_count=chunk.token_count,
                char_count=chunk.char_count,
                nws_count=chunk.nws_count,
            )
            for idx, chunk in enumerate(chunks)
        ]


def _split_hybrid_segments(content: str) -> list[tuple[int, int, str]]:
    if "# %%" in content:
        return _split_by_cells(content)

    docstring_matches = list(
        re.finditer(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', content)
    )
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


def _rebase_chunks(content: str, segment_char_start: int, chunks: list[Chunk]) -> list[Chunk]:
    if not chunks:
        return []

    segment_byte_start = len(content[:segment_char_start].encode("utf-8"))
    line_offset = content.count("\n", 0, segment_char_start)

    out: list[Chunk] = []
    for chunk in chunks:
        out.append(
            Chunk(
                text=chunk.text,
                contextualized_text=chunk.contextualized_text,
                byte_range=ByteRange(
                    start=segment_byte_start + chunk.byte_range.start,
                    end=segment_byte_start + chunk.byte_range.end,
                ),
                line_range=LineRange(
                    start=line_offset + chunk.line_range.start,
                    end=line_offset + chunk.line_range.end,
                ),
                index=chunk.index,
                total_chunks=chunk.total_chunks,
                context=chunk.context,
                token_count=chunk.token_count,
                char_count=chunk.char_count,
                nws_count=chunk.nws_count,
            )
        )

    return out
