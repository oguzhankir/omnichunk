from __future__ import annotations

import re
from typing import Callable

from omnichunk.context.format import format_contextualized_text
from omnichunk.parser.markdown_parser import ProseNode, parse_markdown
from omnichunk.sizing.counter import make_size_counter, make_token_counter
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
from omnichunk.windowing.overlap import build_line_overlap_text

_SPLIT_HIERARCHY: list[str] = [
    r"(?:\r?\n){2,}",
    r"\t+",
    r"\s+",
    r"[\.\?!\*]+",
    r"[;,\(\)\[\]\"'`]+",
    r"[:—…]+",
    r"[/\\–&-]+",
    r"",
]


class ProseEngine:
    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        if not content.strip():
            return []

        language = options.language or detect_language(filepath=filepath, content=content)
        size_counter = make_size_counter(
            options.size_unit,
            tokenizer=options.tokenizer,
            chunk_size=options.max_chunk_size,
        )
        token_counter = make_token_counter(options.tokenizer, chunk_size=options.max_chunk_size)

        if language == "markdown":
            _, nodes = parse_markdown(content)
        else:
            nodes = _plaintext_nodes(content)

        windows = _build_node_windows(
            nodes,
            max_size=options.max_chunk_size,
            min_size=options.min_chunk_size,
            size_counter=size_counter,
            content=content,
        )

        if not windows:
            windows = [[(0, len(content), [])]]

        ranges = _windows_to_contiguous_ranges(windows, len(content))
        ranges = _filter_empty_ranges(content, ranges)

        cumsum = preprocess_nws_cumsum(content)
        chunks: list[Chunk] = []
        previous_text = ""

        for start, end, hierarchy, section_type in ranges:
            if end <= start:
                continue

            text = content[start:end]
            if not text.strip():
                continue

            line_start = content.count("\n", 0, start)
            line_end = content.count("\n", 0, end)
            context = ChunkContext(
                filepath=filepath,
                language=language,  # type: ignore[arg-type]
                content_type=ContentType.PROSE,
                heading_hierarchy=hierarchy,
                section_type=section_type,
                entities=_entities_for_section(section_type, text, start, end, line_start, line_end),
            )

            overlap_text = build_line_overlap_text(previous_text, options.overlap_lines)
            contextualized_text = (
                text
                if options.context_mode == "none"
                else format_contextualized_text(text, context=context, overlap_text=overlap_text)
            )

            encoded = content.encode("utf-8")
            byte_start = len(content[:start].encode("utf-8"))
            byte_end = len(content[:end].encode("utf-8"))

            chunks.append(
                Chunk(
                    text=text,
                    contextualized_text=contextualized_text,
                    byte_range=ByteRange(byte_start, byte_end),
                    line_range=LineRange(line_start, max(line_start, line_end)),
                    index=len(chunks),
                    total_chunks=-1,
                    context=context,
                    token_count=token_counter(text),
                    char_count=len(text),
                    nws_count=get_nws_count(cumsum, byte_start, byte_end),
                )
            )
            previous_text = text

        total = len(chunks)
        return [
            Chunk(
                text=chunk.text,
                contextualized_text=chunk.contextualized_text,
                byte_range=chunk.byte_range,
                line_range=chunk.line_range,
                index=index,
                total_chunks=total,
                context=chunk.context,
                token_count=chunk.token_count,
                char_count=chunk.char_count,
                nws_count=chunk.nws_count,
            )
            for index, chunk in enumerate(chunks)
        ]


def _plaintext_nodes(content: str) -> list[ProseNode]:
    nodes: list[ProseNode] = []
    cursor = 0
    parts = re.split(r"(\n\s*\n)", content)
    for part in parts:
        if not part:
            continue
        start = cursor
        end = cursor + len(part)
        cursor = end
        if not part.strip():
            continue
        line_start = content.count("\n", 0, start)
        line_end = content.count("\n", 0, end)
        nodes.append(
            ProseNode(
                kind=EntityType.PARAGRAPH,
                text=part,
                byte_range=ByteRange(start, end),
                line_range=LineRange(line_start, max(line_start, line_end)),
                heading_hierarchy=[],
            )
        )
    return nodes


def _build_node_windows(
    nodes: list[ProseNode],
    *,
    max_size: int,
    min_size: int,
    size_counter: Callable[[str], int],
    content: str,
) -> list[list[tuple[int, int, list[str], str]]]:
    windows: list[list[tuple[int, int, list[str], str]]] = []
    current: list[tuple[int, int, list[str], str]] = []
    current_size = 0

    for node in nodes:
        node_size = size_counter(node.text)
        node_payload = (
            node.byte_range.start,
            node.byte_range.end,
            list(node.heading_hierarchy),
            node.kind.value,
        )

        if node_size <= max_size and current_size + node_size <= max_size:
            current.append(node_payload)
            current_size += node_size
            continue

        if node_size > max_size:
            if current:
                windows.append(current)
                current = []
                current_size = 0

            split_ranges = _split_oversized_text(
                node.text,
                base_start=node.byte_range.start,
                max_size=max_size,
                size_counter=size_counter,
            )
            windows.extend(
                [
                    [(start, end, list(node.heading_hierarchy), node.kind.value)]
                    for start, end in split_ranges
                    if end > start
                ]
            )
            continue

        if current:
            windows.append(current)
        current = [node_payload]
        current_size = node_size

    if current:
        windows.append(current)

    if len(windows) <= 1:
        return windows

    idx = 0
    while idx < len(windows):
        window = windows[idx]
        size = size_counter(content[window[0][0] : window[-1][1]])
        if size >= min_size:
            idx += 1
            continue

        if idx + 1 < len(windows):
            windows[idx].extend(windows[idx + 1])
            del windows[idx + 1]
            continue

        if idx > 0:
            windows[idx - 1].extend(windows[idx])
            del windows[idx]
            idx -= 1
            continue

        idx += 1

    return windows


def _split_oversized_text(
    text: str,
    *,
    base_start: int,
    max_size: int,
    size_counter: Callable[[str], int],
) -> list[tuple[int, int]]:
    if size_counter(text) <= max_size:
        return [(base_start, base_start + len(text))]

    splits = _hierarchical_split_points(text)
    if not splits:
        splits = list(range(1, len(text)))

    chunks: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        best_end = cursor + 1
        for point in splits:
            if point <= cursor:
                continue
            candidate = text[cursor:point]
            if size_counter(candidate) <= max_size:
                best_end = point
            else:
                break

        if best_end <= cursor:
            best_end = min(len(text), cursor + max_size)

        chunks.append((base_start + cursor, base_start + best_end))
        cursor = best_end

    return chunks


def _hierarchical_split_points(text: str) -> list[int]:
    points: set[int] = set()
    for pattern in _SPLIT_HIERARCHY:
        if not pattern:
            continue
        for match in re.finditer(pattern, text):
            points.add(match.end())
    points.add(len(text))
    return sorted(p for p in points if p > 0)


def _windows_to_contiguous_ranges(
    windows: list[list[tuple[int, int, list[str], str]]],
    total_len: int,
) -> list[tuple[int, int, list[str], str]]:
    if not windows:
        return []

    windows = sorted(windows, key=lambda w: w[0][0])
    ranges: list[tuple[int, int, list[str], str]] = []
    cursor = 0

    for window in windows:
        window_start = min(item[0] for item in window)
        window_end = max(item[1] for item in window)
        hierarchy = next((item[2] for item in window if item[2]), [])
        section_type = window[0][3] if window else "section"
        start = cursor
        end = max(window_end, start)
        if end > start:
            ranges.append((start, end, hierarchy, section_type))
            cursor = end

    if cursor < total_len and ranges:
        start, end, hierarchy, section_type = ranges[-1]
        ranges[-1] = (start, total_len, hierarchy, section_type)
    elif cursor < total_len:
        ranges.append((0, total_len, [], "paragraph"))

    return ranges


def _filter_empty_ranges(
    content: str,
    ranges: list[tuple[int, int, list[str], str]],
) -> list[tuple[int, int, list[str], str]]:
    out: list[tuple[int, int, list[str], str]] = []
    for start, end, hierarchy, section_type in ranges:
        if end <= start:
            continue
        if not content[start:end].strip():
            if out:
                ps, pe, ph, pt = out[-1]
                out[-1] = (ps, end, ph, pt)
            continue
        out.append((start, end, hierarchy, section_type))
    return out


def _entities_for_section(
    section_type: str,
    text: str,
    start: int,
    end: int,
    line_start: int,
    line_end: int,
) -> list[EntityInfo]:
    mapping = {
        "heading": EntityType.HEADING,
        "section": EntityType.SECTION,
        "paragraph": EntityType.PARAGRAPH,
        "list": EntityType.LIST,
        "table": EntityType.TABLE,
        "code_block": EntityType.CODE_BLOCK,
        "frontmatter": EntityType.FRONTMATTER,
    }
    etype = mapping.get(section_type, EntityType.SECTION)
    signature = text.strip().splitlines()[0][:120] if text.strip() else section_type
    return [
        EntityInfo(
            name=section_type,
            type=etype,
            signature=signature,
            byte_range=ByteRange(start, end),
            line_range=LineRange(line_start, max(line_start, line_end)),
        )
    ]
