from __future__ import annotations

import json
import re
from collections.abc import Iterator

from omnichunk.context.format import format_contextualized_text
from omnichunk.parser.html_parser import parse_html_structure
from omnichunk.sizing.counter import make_token_counter
from omnichunk.sizing.nws import get_nws_count, preprocess_nws_cumsum
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkOptions,
    ContentType,
    EntityInfo,
    EntityType,
    LineRange,
)
from omnichunk.util.detect import detect_language
from omnichunk.util.text_index import TextIndex


class MarkupEngine:
    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        chunks = list(self._iter_chunks(filepath, content, options))
        return _finalize_chunk_indexes(chunks)

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        for idx, chunk in enumerate(self._iter_chunks(filepath, content, options)):
            yield _with_unknown_total(chunk, idx)

    def _iter_chunks(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        if not content.strip():
            return

        language = options.language or detect_language(filepath=filepath, content=content)
        ranges = _split_markup(content, language)
        if not ranges:
            ranges = [(0, len(content), [])]

        ranges = _merge_small_ranges(
            content, ranges, options.max_chunk_size, options.min_chunk_size
        )

        token_counter = make_token_counter(options.tokenizer, chunk_size=options.max_chunk_size)
        cumsum = options._precomputed_nws_cumsum
        if cumsum is None:
            cumsum = preprocess_nws_cumsum(content, backend=options.nws_backend)

        precomputed_text_index = options._precomputed_text_index
        if isinstance(precomputed_text_index, TextIndex):
            text_index = precomputed_text_index
        else:
            text_index = TextIndex(content)

        chunk_index = 0

        for start, end, breadcrumb in ranges:
            text = content[start:end]
            if not text.strip():
                continue

            line_start = text_index.line_for_char(start)
            line_end = text_index.line_for_char(max(start, end - 1))
            byte_start = text_index.byte_offset_for_char(start)
            byte_end = text_index.byte_offset_for_char(end)

            section_type: str = language
            if language == "json":
                section_type = "json_object"
            elif language in {"yaml", "toml"}:
                section_type = "mapping"
            elif language in {"html", "xml"}:
                section_type = "element"

            context = ChunkContext(
                filepath=filepath,
                language=language,
                content_type=ContentType.MARKUP,
                breadcrumb=breadcrumb,
                section_type=section_type,
                entities=[
                    EntityInfo(
                        name=(breadcrumb[-1] if breadcrumb else section_type),
                        type=EntityType.SECTION,
                        signature=(breadcrumb[-1] if breadcrumb else section_type),
                        byte_range=ByteRange(byte_start, byte_end),
                        line_range=LineRange(line_start, max(line_start, line_end)),
                    )
                ],
            )

            contextualized_text = (
                text
                if options.context_mode == "none"
                else format_contextualized_text(text, context=context)
            )

            yield Chunk(
                text=text,
                contextualized_text=contextualized_text,
                byte_range=ByteRange(byte_start, byte_end),
                line_range=LineRange(line_start, max(line_start, line_end)),
                index=chunk_index,
                total_chunks=-1,
                context=context,
                token_count=token_counter(text),
                char_count=len(text),
                nws_count=get_nws_count(cumsum, byte_start, byte_end),
            )
            chunk_index += 1


def _split_markup(content: str, language: str) -> list[tuple[int, int, list[str]]]:
    if language == "json":
        return _split_json(content)
    if language in {"yaml", "yml"}:
        return _split_yaml(content)
    if language == "toml":
        return _split_toml(content)
    if language in {"html", "xml"}:
        return _split_html_like(content)
    return [(0, len(content), [])]


def _split_json(content: str) -> list[tuple[int, int, list[str]]]:
    try:
        parsed = json.loads(content)
    except Exception:
        return [(0, len(content), [])]

    if not isinstance(parsed, dict):
        return [(0, len(content), [])]

    out: list[tuple[int, int, list[str]]] = []
    for key in parsed:
        pattern = re.compile(rf'"{re.escape(str(key))}"\s*:')
        match = pattern.search(content)
        if not match:
            continue
        start = match.start()
        end = _find_json_value_end(content, match.end())
        out.append((start, end, [str(key)]))

    if not out:
        return [(0, len(content), [])]

    out.sort(key=lambda t: t[0])
    return _normalize_ranges(out, len(content))


def _find_json_value_end(content: str, idx: int) -> int:
    depth_curly = 0
    depth_square = 0
    in_string = False
    escape = False

    for pos in range(idx, len(content)):
        ch = content[pos]
        if in_string:
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth_curly += 1
        elif ch == "}":
            if depth_curly == 0 and depth_square == 0:
                return pos
            depth_curly = max(0, depth_curly - 1)
        elif ch == "[":
            depth_square += 1
        elif ch == "]":
            depth_square = max(0, depth_square - 1)
        elif ch == "," and depth_curly == 0 and depth_square == 0:
            return pos + 1

    return len(content)


def _split_yaml(content: str) -> list[tuple[int, int, list[str]]]:
    matches = list(re.finditer(r"(?m)^([\w\-.]+)\s*:\s*", content))
    if not matches:
        return [(0, len(content), [])]

    ranges: list[tuple[int, int, list[str]]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        key = match.group(1)
        ranges.append((start, end, [key]))
    return _normalize_ranges(ranges, len(content))


def _split_toml(content: str) -> list[tuple[int, int, list[str]]]:
    matches = list(re.finditer(r"(?m)^\[([^\]]+)\]\s*$", content))
    if not matches:
        return [(0, len(content), [])]

    ranges: list[tuple[int, int, list[str]]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        name = match.group(1).strip()
        ranges.append((start, end, name.split(".")))
    return _normalize_ranges(ranges, len(content))


def _split_html_like(content: str) -> list[tuple[int, int, list[str]]]:
    nodes = parse_html_structure(content)
    if not nodes:
        return [(0, len(content), [])]

    semantic_tags = {
        "section",
        "article",
        "main",
        "div",
        "body",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
    ranges: list[tuple[int, int, list[str]]] = []

    for node in nodes:
        if node.tag not in semantic_tags:
            continue
        start = node.byte_range.start
        end = node.byte_range.end
        ranges.append((start, end, node.path))

    if not ranges:
        return [(0, len(content), [])]

    return _normalize_ranges(ranges, len(content))


def _normalize_ranges(
    ranges: list[tuple[int, int, list[str]]], total_len: int
) -> list[tuple[int, int, list[str]]]:
    ranges.sort(key=lambda t: t[0])
    out: list[tuple[int, int, list[str]]] = []
    cursor = 0

    for start, end, breadcrumb in ranges:
        start = max(0, min(start, total_len))
        end = max(start, min(end, total_len))
        if end <= cursor:
            continue

        segment_start = cursor
        segment_end = max(cursor, end)
        if segment_end <= segment_start:
            continue

        out.append((segment_start, segment_end, breadcrumb))
        cursor = end

    if cursor < total_len:
        if out:
            s, _, b = out[-1]
            out[-1] = (s, total_len, b)
        else:
            out.append((0, total_len, []))

    if not out and total_len > 0:
        out.append((0, total_len, []))

    return out


def _merge_small_ranges(
    content: str,
    ranges: list[tuple[int, int, list[str]]],
    max_chunk_size: int,
    min_chunk_size: int,
) -> list[tuple[int, int, list[str]]]:
    if not ranges:
        return []

    merged: list[tuple[int, int, list[str]]] = []
    for start, end, breadcrumb in ranges:
        if not merged:
            merged.append((start, end, breadcrumb))
            continue

        ps, pe, pb = merged[-1]
        if (end - ps) <= max_chunk_size:
            merged[-1] = (ps, end, pb or breadcrumb)
        else:
            merged.append((start, end, breadcrumb))

    idx = 0
    while idx < len(merged):
        start, end, breadcrumb = merged[idx]
        if (end - start) >= min_chunk_size:
            idx += 1
            continue
        if idx + 1 < len(merged):
            _, next_end, next_breadcrumb = merged[idx + 1]
            merged[idx] = (start, next_end, breadcrumb or next_breadcrumb)
            del merged[idx + 1]
            continue
        if idx > 0:
            prev_start, _, prev_breadcrumb = merged[idx - 1]
            merged[idx - 1] = (prev_start, end, prev_breadcrumb or breadcrumb)
            del merged[idx]
            idx -= 1
            continue
        idx += 1

    return _normalize_ranges(merged, len(content))


def _finalize_chunk_indexes(chunks: list[Chunk]) -> list[Chunk]:
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
