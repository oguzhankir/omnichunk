from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

from omnichunk.context.format import format_contextualized_text
from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.markup_engine import MarkupEngine
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
    Language,
    LineRange,
)
from omnichunk.util.detect import detect_language
from omnichunk.util.text_index import TextIndex
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

_CODE_FENCE_LANGUAGE_ALIASES: dict[str, str] = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "tsx": "typescript",
    "rs": "rust",
    "rust": "rust",
    "go": "go",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "cs": "csharp",
    "csharp": "csharp",
    "rb": "ruby",
    "ruby": "ruby",
    "php": "php",
    "kt": "kotlin",
    "kotlin": "kotlin",
    "swift": "swift",
}

_CODE_LANGUAGES: set[str] = {
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
    "kotlin",
    "swift",
    "scala",
    "haskell",
    "lua",
    "zig",
    "elixir",
}

_MARKUP_FENCE_LANGUAGE_ALIASES: dict[str, str] = {
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "toml": "toml",
    "html": "html",
    "xml": "xml",
}

_MARKUP_LANGUAGES: set[str] = {"json", "yaml", "toml", "html", "xml"}


class ProseEngine:
    def __init__(self) -> None:
        self._code_engine = CodeEngine()
        self._markup_engine = MarkupEngine()

    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        chunks = list(self._iter_chunks(filepath, content, options))
        return _finalize_chunk_indexes(chunks)

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        for idx, chunk in enumerate(self._iter_chunks(filepath, content, options)):
            yield _with_unknown_total(chunk, idx)

    def _iter_chunks(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        if not content.strip():
            return

        text_index = TextIndex(content)
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
            nodes = _plaintext_nodes(content, text_index)

        windows = _build_node_windows(
            nodes,
            max_size=options.max_chunk_size,
            min_size=options.min_chunk_size,
            size_counter=size_counter,
            content=content,
            preserve_code_blocks=(language == "markdown"),
        )

        if not windows:
            windows = [[(0, len(content), [], "paragraph")]]

        ranges = _windows_to_contiguous_ranges(windows, len(content))
        ranges = _filter_empty_ranges(content, ranges)

        cumsum = preprocess_nws_cumsum(content)
        previous_text = ""
        chunk_index = 0

        for start, end, hierarchy, section_type in ranges:
            if end <= start:
                continue

            text = content[start:end]
            if not text.strip():
                continue

            if language == "markdown" and section_type == EntityType.CODE_BLOCK.value:
                code_chunks = self._chunk_markdown_code_block(
                    filepath=filepath,
                    block_text=text,
                    block_char_start=start,
                    heading_hierarchy=hierarchy,
                    options=options,
                    text_index=text_index,
                    cumsum=cumsum,
                    start_index=chunk_index,
                )
                if code_chunks:
                    for chunk in code_chunks:
                        yield chunk
                        previous_text = chunk.text
                        chunk_index += 1
                    continue

            line_start = text_index.line_for_char(start)
            line_end = text_index.line_for_char(max(start, end - 1))
            context = ChunkContext(
                filepath=filepath,
                language=language,
                content_type=ContentType.PROSE,
                heading_hierarchy=hierarchy,
                section_type=section_type,
                entities=_entities_for_section(
                    section_type, text, start, end, line_start, line_end
                ),
            )

            overlap_text = build_line_overlap_text(previous_text, options.overlap_lines)
            contextualized_text = (
                text
                if options.context_mode == "none"
                else format_contextualized_text(text, context=context, overlap_text=overlap_text)
            )

            byte_start = text_index.byte_offset_for_char(start)
            byte_end = text_index.byte_offset_for_char(end)

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
            previous_text = text
            chunk_index += 1

    def _chunk_markdown_code_block(
        self,
        *,
        filepath: str,
        block_text: str,
        block_char_start: int,
        heading_hierarchy: list[str],
        options: ChunkOptions,
        text_index: TextIndex,
        cumsum: Any,
        start_index: int,
    ) -> list[Chunk]:
        parts = _split_fenced_code_block(block_text)
        if parts is None:
            return []

        prefix_text, code_text, suffix_text, fence_language = parts
        token_counter = make_token_counter(options.tokenizer, chunk_size=options.max_chunk_size)
        chunks: list[Chunk] = []

        cursor = block_char_start

        if prefix_text and prefix_text.strip():
            prefix_start = cursor
            prefix_end = prefix_start + len(prefix_text)
            chunks.append(
                _build_markdown_fence_chunk(
                    filepath=filepath,
                    language=options.language or "markdown",
                    text=prefix_text,
                    heading_hierarchy=heading_hierarchy,
                    start_char=prefix_start,
                    end_char=prefix_end,
                    index=start_index + len(chunks),
                    options=options,
                    text_index=text_index,
                    cumsum=cumsum,
                    token_counter=token_counter,
                )
            )
        cursor += len(prefix_text)

        if code_text:
            resolved_language = _resolve_code_fence_language(fence_language, code_text)
            if resolved_language is not None:
                sub_options = replace(options, content_type=ContentType.CODE, overlap_lines=0)
                sub_options.language = resolved_language  # type: ignore[assignment]

                code_chunks = list(self._code_engine.stream(filepath, code_text, sub_options))
                delegated = _rebase_delegated_fence_chunks(
                    delegated_chunks=code_chunks,
                    heading_hierarchy=heading_hierarchy,
                    options=options,
                    text_index=text_index,
                    byte_offset=text_index.byte_offset_for_char(cursor),
                    cumsum=cumsum,
                    start_index=start_index + len(chunks),
                )
                if delegated:
                    chunks.extend(delegated)
                elif code_text.strip():
                    code_start = cursor
                    code_end = code_start + len(code_text)
                    chunks.append(
                        _build_markdown_fence_chunk(
                            filepath=filepath,
                            language=options.language or "markdown",
                            text=code_text,
                            heading_hierarchy=heading_hierarchy,
                            start_char=code_start,
                            end_char=code_end,
                            index=start_index + len(chunks),
                            options=options,
                            text_index=text_index,
                            cumsum=cumsum,
                            token_counter=token_counter,
                        )
                    )
            else:
                resolved_markup_language = _resolve_markup_fence_language(fence_language, code_text)
                if resolved_markup_language is not None:
                    sub_options = replace(options, content_type=ContentType.MARKUP, overlap_lines=0)
                    sub_options.language = resolved_markup_language  # type: ignore[assignment]

                    markup_chunks = list(
                        self._markup_engine.stream(filepath, code_text, sub_options)
                    )
                    delegated = _rebase_delegated_fence_chunks(
                        delegated_chunks=markup_chunks,
                        heading_hierarchy=heading_hierarchy,
                        options=options,
                        text_index=text_index,
                        byte_offset=text_index.byte_offset_for_char(cursor),
                        cumsum=cumsum,
                        start_index=start_index + len(chunks),
                    )
                    if delegated:
                        chunks.extend(delegated)
                    elif code_text.strip():
                        code_start = cursor
                        code_end = code_start + len(code_text)
                        chunks.append(
                            _build_markdown_fence_chunk(
                                filepath=filepath,
                                language=options.language or "markdown",
                                text=code_text,
                                heading_hierarchy=heading_hierarchy,
                                start_char=code_start,
                                end_char=code_end,
                                index=start_index + len(chunks),
                                options=options,
                                text_index=text_index,
                                cumsum=cumsum,
                                token_counter=token_counter,
                            )
                        )
                elif code_text.strip():
                    code_start = cursor
                    code_end = code_start + len(code_text)
                    chunks.append(
                        _build_markdown_fence_chunk(
                            filepath=filepath,
                            language=options.language or "markdown",
                            text=code_text,
                            heading_hierarchy=heading_hierarchy,
                            start_char=code_start,
                            end_char=code_end,
                            index=start_index + len(chunks),
                            options=options,
                            text_index=text_index,
                            cumsum=cumsum,
                            token_counter=token_counter,
                        )
                    )
        cursor += len(code_text)

        if suffix_text and suffix_text.strip():
            suffix_start = cursor
            suffix_end = suffix_start + len(suffix_text)
            chunks.append(
                _build_markdown_fence_chunk(
                    filepath=filepath,
                    language=options.language or "markdown",
                    text=suffix_text,
                    heading_hierarchy=heading_hierarchy,
                    start_char=suffix_start,
                    end_char=suffix_end,
                    index=start_index + len(chunks),
                    options=options,
                    text_index=text_index,
                    cumsum=cumsum,
                    token_counter=token_counter,
                )
            )

        return chunks


def _plaintext_nodes(content: str, text_index: TextIndex | None = None) -> list[ProseNode]:
    nodes: list[ProseNode] = []
    index = text_index or TextIndex(content)
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
        line_start = index.line_for_char(start)
        line_end = index.line_for_char(max(start, end - 1))
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
    preserve_code_blocks: bool = False,
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

        if preserve_code_blocks and node.kind == EntityType.CODE_BLOCK:
            if current:
                windows.append(current)
                current = []
                current_size = 0
            windows.append([node_payload])
            continue

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
        if preserve_code_blocks and _window_has_section_type(window, EntityType.CODE_BLOCK.value):
            idx += 1
            continue

        size = size_counter(content[window[0][0] : window[-1][1]])
        if size >= min_size:
            idx += 1
            continue

        if idx + 1 < len(windows):
            if preserve_code_blocks and _window_has_section_type(
                windows[idx + 1], EntityType.CODE_BLOCK.value
            ):
                idx += 1
                continue
            windows[idx].extend(windows[idx + 1])
            del windows[idx + 1]
            continue

        if idx > 0:
            if preserve_code_blocks and _window_has_section_type(
                windows[idx - 1], EntityType.CODE_BLOCK.value
            ):
                idx += 1
                continue
            windows[idx - 1].extend(windows[idx])
            del windows[idx]
            idx -= 1
            continue

        idx += 1

    return windows


def _window_has_section_type(
    window: list[tuple[int, int, list[str], str]], section_type: str
) -> bool:
    return any(item[3] == section_type for item in window)


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
        min(item[0] for item in window)
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


def _split_fenced_code_block(block_text: str) -> tuple[str, str, str, str] | None:
    lines = block_text.splitlines(keepends=True)
    if len(lines) < 2:
        return None
    opening = lines[0]
    if not opening.strip().startswith("```"):
        return None

    close_idx: int | None = None
    for idx in range(len(lines) - 1, 0, -1):
        if lines[idx].strip().startswith("```"):
            close_idx = idx
            break

    if close_idx is None:
        return None

    prefix = opening
    code = "".join(lines[1:close_idx])
    suffix = "".join(lines[close_idx:])

    fence_language = opening.strip()[3:].strip().lower()
    if code and not code.strip():
        prefix = prefix + code
        code = ""

    return prefix, code, suffix, fence_language


def _resolve_code_fence_language(fence_language: str, code_text: str) -> str | None:
    tag = fence_language.strip().lower()
    if tag:
        mapped = _CODE_FENCE_LANGUAGE_ALIASES.get(tag, tag)
        if mapped in _CODE_LANGUAGES:
            return mapped

    detected = detect_language(filepath="", content=code_text)
    if detected in _CODE_LANGUAGES:
        return detected

    return None


def _resolve_markup_fence_language(fence_language: str, block_text: str) -> str | None:
    tag = fence_language.strip().lower()
    if tag:
        mapped = _MARKUP_FENCE_LANGUAGE_ALIASES.get(tag, tag)
        if mapped in _MARKUP_LANGUAGES:
            return mapped

    detected = detect_language(filepath="", content=block_text)
    if detected in _MARKUP_LANGUAGES:
        return detected

    return None


def _rebase_delegated_fence_chunks(
    *,
    delegated_chunks: list[Chunk],
    heading_hierarchy: list[str],
    options: ChunkOptions,
    text_index: TextIndex,
    byte_offset: int,
    cumsum: Any,
    start_index: int,
) -> list[Chunk]:
    out: list[Chunk] = []
    for chunk in delegated_chunks:
        byte_start = byte_offset + chunk.byte_range.start
        byte_end = byte_offset + chunk.byte_range.end

        context = replace(
            chunk.context,
            heading_hierarchy=list(heading_hierarchy),
            section_type=EntityType.CODE_BLOCK.value,
        )
        contextualized_text = (
            chunk.text
            if options.context_mode == "none"
            else format_contextualized_text(chunk.text, context=context)
        )

        out.append(
            Chunk(
                text=chunk.text,
                contextualized_text=contextualized_text,
                byte_range=ByteRange(byte_start, byte_end),
                line_range=LineRange(
                    text_index.line_for_byte(byte_start),
                    text_index.line_for_byte(max(byte_start, byte_end - 1)),
                ),
                index=start_index + len(out),
                total_chunks=-1,
                context=context,
                token_count=chunk.token_count,
                char_count=len(chunk.text),
                nws_count=get_nws_count(cumsum, byte_start, byte_end),
            )
        )

    return out


def _build_markdown_fence_chunk(
    *,
    filepath: str,
    language: Language,
    text: str,
    heading_hierarchy: list[str],
    start_char: int,
    end_char: int,
    index: int,
    options: ChunkOptions,
    text_index: TextIndex,
    cumsum: Any,
    token_counter: Callable[[str], int],
) -> Chunk:
    byte_start = text_index.byte_offset_for_char(start_char)
    byte_end = text_index.byte_offset_for_char(end_char)
    line_start = text_index.line_for_char(start_char)
    line_end = text_index.line_for_char(max(start_char, end_char - 1))

    context = ChunkContext(
        filepath=filepath,
        language=language,
        content_type=ContentType.PROSE,
        heading_hierarchy=list(heading_hierarchy),
        section_type=EntityType.CODE_BLOCK.value,
        entities=_entities_for_section(
            EntityType.CODE_BLOCK.value,
            text,
            byte_start,
            byte_end,
            line_start,
            line_end,
        ),
    )

    contextualized_text = (
        text
        if options.context_mode == "none"
        else format_contextualized_text(text, context=context)
    )

    return Chunk(
        text=text,
        contextualized_text=contextualized_text,
        byte_range=ByteRange(byte_start, byte_end),
        line_range=LineRange(line_start, max(line_start, line_end)),
        index=index,
        total_chunks=-1,
        context=context,
        token_count=token_counter(text),
        char_count=len(text),
        nws_count=get_nws_count(cumsum, byte_start, byte_end),
    )


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
