from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

from omnichunk.context.format import format_contextualized_text
from omnichunk.context.rebase import rebase_chunk
from omnichunk.engine.code_engine import CodeEngine
from omnichunk.engine.markup_engine import MarkupEngine
from omnichunk.parser.markdown_parser import ProseNode, parse_markdown
from omnichunk.semantic.sentences import split_sentences
from omnichunk.sizing.counter import find_fitting_prefix, make_size_counter, make_token_counter
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

_SPLIT_HIERARCHY: list[re.Pattern[str] | None] = [
    re.compile(r"(?:\r?\n[ \t]*){2,}"),
    re.compile(r"\r?\n"),
    None,  # Unicode sentence boundaries, before word-level fallbacks.
    re.compile(r"[;；]+"),  # Strong clause boundaries before splitting into words.
    re.compile(r"\s+"),
    re.compile(r"[,，、\(\)\[\]\"'`]+"),
    re.compile(r"[:：—…]+"),
    re.compile(r"[/\\–&-]+"),
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

        precomputed_text_index = options._precomputed_text_index
        if isinstance(precomputed_text_index, TextIndex):
            text_index = precomputed_text_index
        else:
            text_index = TextIndex(content)

        language = options.language or detect_language(filepath=filepath, content=content)
        size_counter = make_size_counter(
            options.size_unit,
            tokenizer=options.tokenizer,
            chunk_size=options.max_chunk_size,
            # Grouping probes progressively longer source slices. Retaining all
            # of them in the token LRU would use quadratic memory per window.
            cache_maxsize=0,
        )
        token_counter = make_token_counter(options.tokenizer, chunk_size=options.max_chunk_size)

        if language == "markdown":
            _, nodes = parse_markdown(content)
            nodes = _markdown_paragraph_nodes(nodes, text_index)
        else:
            nodes = _plaintext_nodes(content, text_index)

        windows = _build_node_windows(
            nodes,
            max_size=options.max_chunk_size,
            min_size=options.min_chunk_size,
            size_counter=size_counter,
            content=content,
            preserve_code_blocks=(language == "markdown"),
            preserve_paragraphs=(
                language == "markdown" and options.markdown_paragraph_policy == "preserve"
            ),
            pack_paragraphs=(
                language == "markdown" and options.markdown_paragraph_policy == "pack"
            ),
            compact_sentences=options.prose_boundary_policy == "compact",
            split_oversized=options.overflow_policy == "split",
        )

        if not windows:
            windows = [[(0, len(content), [], "paragraph")]]

        ranges = _windows_to_contiguous_ranges(windows, len(content))
        ranges = _filter_empty_ranges(content, ranges)

        cumsum = options._precomputed_nws_cumsum
        if cumsum is None:
            cumsum = preprocess_nws_cumsum(content, backend=options.nws_backend)

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

            format_metadata: dict[str, object] = {}
            effective_section_type = section_type
            if language == "markdown":
                if section_type == EntityType.FRONTMATTER.value:
                    from omnichunk.parser.markdown_parser import _parse_yaml_frontmatter

                    body = text.strip().strip("-").strip()
                    parsed = _parse_yaml_frontmatter(body)
                    if parsed:
                        format_metadata["front_matter"] = parsed
                else:
                    from omnichunk.parser.markdown_parser import _detect_callout_kind

                    callout = _detect_callout_kind(text)
                    if callout is not None:
                        effective_section_type = f"callout/{callout}"
                        format_metadata["callout"] = callout

            byte_start = text_index.byte_offset_for_char(start)
            byte_end = text_index.byte_offset_for_char(end)
            context = ChunkContext(
                filepath=filepath,
                language=language,
                content_type=ContentType.PROSE,
                heading_hierarchy=hierarchy,
                section_type=effective_section_type,
                entities=_entities_for_section(
                    section_type, text, byte_start, byte_end, line_start, line_end
                ),
                format_metadata=format_metadata,
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
        delegated_text_index = TextIndex(code_text) if code_text else None
        delegated_cumsum = (
            preprocess_nws_cumsum(code_text, backend=options.nws_backend) if code_text else None
        )

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
                sub_options = replace(
                    options,
                    content_type=ContentType.CODE,
                    overlap_lines=0,
                    _precomputed_text_index=delegated_text_index,
                    _precomputed_nws_cumsum=delegated_cumsum,
                )
                sub_options = replace(sub_options, language=resolved_language)  # type: ignore[arg-type]

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
                    sub_options = replace(
                        options,
                        content_type=ContentType.MARKUP,
                        overlap_lines=0,
                        _precomputed_text_index=delegated_text_index,
                        _precomputed_nws_cumsum=delegated_cumsum,
                    )
                    sub_options = replace(sub_options, language=resolved_markup_language)  # type: ignore[arg-type]

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


def _markdown_paragraph_nodes(nodes: list[ProseNode], text_index: TextIndex) -> list[ProseNode]:
    """Retain blank-line paragraph identities inside plain Markdown body nodes."""
    out: list[ProseNode] = []
    pattern = _SPLIT_HIERARCHY[0]
    assert pattern is not None
    for node in nodes:
        if node.kind != EntityType.PARAGRAPH:
            out.append(node)
            continue
        first_content = len(node.text) - len(node.text.lstrip())
        last_content = len(node.text.rstrip())
        ends = [
            match.end()
            for match in pattern.finditer(node.text)
            if first_content < match.end() < last_content
        ]
        ends.append(len(node.text))
        cursor = 0
        for end in ends:
            start_char = node.byte_range.start + cursor
            end_char = node.byte_range.start + end
            out.append(
                replace(
                    node,
                    text=node.text[cursor:end],
                    byte_range=ByteRange(start_char, end_char),
                    line_range=LineRange(
                        text_index.line_for_char(start_char),
                        text_index.line_for_char(max(start_char, end_char - 1)),
                    ),
                )
            )
            cursor = end
    return out


def _build_node_windows(
    nodes: list[ProseNode],
    *,
    max_size: int,
    min_size: int,
    size_counter: Callable[[str], int],
    content: str,
    preserve_code_blocks: bool = False,
    preserve_paragraphs: bool = False,
    pack_paragraphs: bool = False,
    compact_sentences: bool = False,
    split_oversized: bool = True,
) -> list[list[tuple[int, int, list[str], str]]]:
    windows: list[list[tuple[int, int, list[str], str]]] = []
    current: list[tuple[int, int, list[str], str]] = []
    cursor = 0

    for node_index, node in enumerate(nodes):
        # Own the actual contiguous source, including parser-omitted trivia.
        # Summing individual node sizes loses gaps and assumes additive tokens.
        end = len(content) if node_index == len(nodes) - 1 else node.byte_range.end
        if end <= cursor:
            continue
        start, cursor = cursor, end
        node_text = content[start:end]
        node_size = size_counter(node_text)
        node_payload = (
            start,
            end,
            list(node.heading_hierarchy),
            node.kind.value,
        )

        if preserve_code_blocks and node.kind == EntityType.CODE_BLOCK:
            if current:
                windows.append(current)
                current = []
            windows.append([node_payload])
            continue

        if (
            pack_paragraphs
            and current
            and any(item[3] != EntityType.HEADING.value for item in current)
            and (
                node.kind != EntityType.PARAGRAPH
                or any(
                    item[3] not in {EntityType.HEADING.value, EntityType.PARAGRAPH.value}
                    for item in current
                )
                or current[-1][2] != node.heading_hierarchy
            )
        ):
            # Compact only adjacent prose under the same owning heading. Tables,
            # lists and heading transitions retain their own retrieval identity.
            windows.append(current)
            current = []

        if (
            preserve_paragraphs
            and current
            and any(item[3] != EntityType.HEADING.value for item in current)
        ):
            # A heading belongs to its following body. Distinct body paragraphs
            # keep separate retrieval identities even when spare capacity exists.
            windows.append(current)
            current = []

        combined_start = current[0][0] if current else start
        if size_counter(content[combined_start:end]) <= max_size:
            current.append(node_payload)
            continue

        if node_size > max_size:
            if not split_oversized:
                if current:
                    windows.append(current)
                    current = []
                # Keep an oversized structural unit intact so finalization can
                # enforce the explicit error/preserve policy.
                windows.append([node_payload])
                continue

            split_ranges = None
            split_payloads = [node_payload]
            if (
                current
                and all(item[3] == EntityType.HEADING.value for item in current)
                and node.kind in {EntityType.PARAGRAPH, EntityType.TABLE, EntityType.LIST}
            ):
                # Give a pending heading the first complete fitting body unit.
                # Splitting the body alone can fill its first fragment with two
                # paragraphs, stranding a heading which fits with the first one.
                prefixed_ranges = _split_oversized_text(
                    content[combined_start:end],
                    base_start=combined_start,
                    max_size=max_size,
                    size_counter=size_counter,
                    compact_sentences=compact_sentences,
                )
                if content[start : prefixed_ranges[0][1]].strip():
                    split_ranges = prefixed_ranges
                    split_payloads = [*current, node_payload]
                    current = []

            if current:
                windows.append(current)
                current = []
            if split_ranges is None:
                split_ranges = _split_oversized_text(
                    node_text,
                    base_start=start,
                    max_size=max_size,
                    size_counter=size_counter,
                    compact_sentences=compact_sentences,
                )
            for split_start, split_end in split_ranges:
                # Keep each source piece's original hierarchy and section kind
                # when a new range contains both heading and body text.
                windows.append(
                    [
                        (max(split_start, left), min(split_end, right), hierarchy, kind)
                        for left, right, hierarchy, kind in split_payloads
                        if max(split_start, left) < min(split_end, right)
                    ]
                )
            continue

        if current:
            windows.append(current)
        current = [node_payload]

    if current:
        windows.append(current)

    if len(windows) <= 1 or preserve_paragraphs or pack_paragraphs:
        # A minimum-size preference must not undo explicit paragraph boundaries.
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
            following = windows[idx + 1]
            if (
                not (
                    preserve_code_blocks
                    and _window_has_section_type(following, EntityType.CODE_BLOCK.value)
                )
                and size_counter(content[window[0][0] : following[-1][1]]) <= max_size
            ):
                windows[idx].extend(following)
                del windows[idx + 1]
                continue

        if idx > 0:
            previous = windows[idx - 1]
            if (
                not (
                    preserve_code_blocks
                    and _window_has_section_type(previous, EntityType.CODE_BLOCK.value)
                )
                and size_counter(content[previous[0][0] : window[-1][1]]) <= max_size
            ):
                previous.extend(window)
                del windows[idx]
                idx -= 1
                continue

        idx += 1

    return windows


def _window_has_section_type(
    window: list[tuple[int, int, list[str], str]], section_type: str
) -> bool:
    return any(item[3] == section_type for item in window)


def _prose_sentence_ends(text: str) -> list[int]:
    """Ignore fallback sentence boundaries inside matched square brackets.

    Match each unescaped pair independently, so a missing outer closer does not
    hide later sentences or invalidate an otherwise balanced inner expression.
    This source-structure guard does not change the semantic sentence splitter.
    """
    ends = [end for _, _, end in split_sentences(text)]
    if len(ends) < 2 or "[" not in text or "]" not in text:
        return ends
    stack: list[int] = []
    opening: set[int] = set()
    closing: set[int] = set()
    escaped = False
    for offset, char in enumerate(text):
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "[":
            stack.append(offset)
        elif char == "]" and stack:
            opening.add(stack.pop() + 1)
            closing.add(offset + 1)
    if not opening:
        return ends
    filtered: list[int] = []
    depth = 0
    candidate = 0
    for offset in range(len(text) + 1):
        if offset in closing:
            depth -= 1
        if offset in opening:
            depth += 1
        if candidate < len(ends) and ends[candidate] == offset:
            if depth == 0:
                filtered.append(offset)
            candidate += 1
    return filtered


def _split_oversized_text(
    text: str,
    *,
    base_start: int,
    max_size: int,
    size_counter: Callable[[str], int],
    _level: int = 0,
    compact_sentences: bool = False,
) -> list[tuple[int, int]]:
    """Pack whole structural units; descend only when a unit cannot fit.

    Separators remain in the source slices. Minimum-size preferences must never
    force a fitting paragraph, line or sentence to be cut by finalization.
    """
    if size_counter(text) <= max_size:
        return [(base_start, base_start + len(text))]

    if _level < len(_SPLIT_HIERARCHY):
        pattern = _SPLIT_HIERARCHY[_level]
        points = (
            _prose_sentence_ends(text)
            if pattern is None
            else [match.end() for match in pattern.finditer(text)]
        )
        # Attach leading/trailing trivia to content instead of creating empty
        # structural units which can perturb packing and source ownership.
        first_content = len(text) - len(text.lstrip())
        last_content = len(text.rstrip())
        points = [point for point in points if first_content < point < last_content]
        points.append(len(text))
        chunks: list[tuple[int, int]] = []
        group_start = unit_start = 0
        for unit_end in points:
            if size_counter(text[group_start:unit_end]) <= max_size:
                unit_start = unit_end
                continue
            if unit_start > group_start:
                chunks.append((base_start + group_start, base_start + unit_start))
            if size_counter(text[unit_start:unit_end]) <= max_size:
                group_start, unit_start = unit_start, unit_end
                continue
            children = _split_oversized_text(
                text[unit_start:unit_end],
                base_start=base_start + unit_start,
                max_size=max_size,
                size_counter=size_counter,
                _level=_level + 1,
                compact_sentences=compact_sentences,
            )
            # Keep the last recursive fragment available for the next complete
            # unit. Flushing it here strands a short sentence/line tail even
            # when the following sentence or row fits in the same payload.
            chunks.extend(children[:-1])
            group_start = children[-1][0] - base_start
            unit_start = unit_end
        if group_start < len(text):
            chunks.append((base_start + group_start, base_start + len(text)))
        if compact_sentences and pattern is None and len(points) > 1:
            # Compare sentence-first and clause/word-first partitions. Compact
            # mode may split a fitting sentence but never adds fragments here.
            compact = _split_oversized_text(
                text,
                base_start=base_start,
                max_size=max_size,
                size_counter=size_counter,
                _level=_level + 1,
                compact_sentences=compact_sentences,
            )
            if len(compact) <= len(chunks):
                return compact
        return chunks

    chunks = []
    cursor = 0
    while cursor < len(text):
        best_end = find_fitting_prefix(text, cursor, len(text), max_size, size_counter)
        if best_end == cursor:
            # Finalization applies the caller's overflow policy when a complete
            # Unicode character cannot fit the budget.
            best_end = cursor + 1

        chunks.append((base_start + cursor, base_start + best_end))
        cursor = best_end

    return chunks


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
        window_end = max(item[1] for item in window)
        hierarchy = next((item[2] for item in reversed(window) if item[2]), [])
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
    if not lines:
        return None
    opening_index = next((i for i, line in enumerate(lines) if line.strip()), 0)
    opening = lines[opening_index]
    match = re.fullmatch(r"(`{3,}|~{3,})([^\r\n]*)", opening.strip())
    if match is None:
        return None
    fence, info = match.groups()

    close_idx: int | None = None
    for idx in range(opening_index + 1, len(lines)):
        candidate = lines[idx].strip()
        if len(candidate) >= len(fence) and set(candidate) == {fence[0]}:
            close_idx = idx
            break

    prefix = "".join(lines[: opening_index + 1])
    code = "".join(lines[opening_index + 1 : close_idx])
    suffix = "".join(lines[close_idx:]) if close_idx is not None else ""

    fence_language = info.strip().split(maxsplit=1)[0].lower() if info.strip() else ""
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
        chunk = rebase_chunk(chunk, text_index, byte_offset)
        byte_start = chunk.byte_range.start
        byte_end = chunk.byte_range.end

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
            replace(
                chunk,
                contextualized_text=contextualized_text,
                byte_range=ByteRange(byte_start, byte_end),
                line_range=LineRange(
                    text_index.line_for_byte(byte_start),
                    text_index.line_for_byte(max(byte_start, byte_end - 1)),
                ),
                index=start_index + len(out),
                total_chunks=-1,
                context=context,
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
