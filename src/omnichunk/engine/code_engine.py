from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any

from omnichunk.context.entities import enrich_parent_links, extract_entities
from omnichunk.context.format import format_contextualized_text
from omnichunk.context.imports import build_import_infos, filter_imports_for_chunk
from omnichunk.context.range_index import EntityRangeSweep
from omnichunk.context.scope import build_scope_tree, find_scope_chain
from omnichunk.context.siblings import SiblingIndex, build_sibling_index, detect_siblings_for_chunk
from omnichunk.parser.tree_sitter import parse_code
from omnichunk.semantic.sentences import split_sentences
from omnichunk.sizing.counter import make_size_counter, make_token_counter
from omnichunk.sizing.nws import get_nws_count, preprocess_nws_cumsum
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkOptions,
    ContentType,
    EntityInfo,
    LineRange,
)
from omnichunk.util.detect import detect_language
from omnichunk.util.text_index import TextIndex
from omnichunk.windowing.greedy import (
    RangeNode,
    assign_windows_for_nodes,
    assign_windows_for_ranges,
)
from omnichunk.windowing.merge import merge_adjacent_windows
from omnichunk.windowing.models import ASTNodeWindowItem, SourceBudget
from omnichunk.windowing.overlap import apply_token_overlap, build_line_overlap_text


@dataclass(frozen=True)
class _CommentGroup(RangeNode):
    """A fitting leading comment block and the statement it describes."""


class CodeEngine:
    def chunk(self, filepath: str, content: str, options: ChunkOptions) -> list[Chunk]:
        chunks = list(self._iter_base_chunks(filepath, content, options))
        chunks = _finalize_chunk_indexes(chunks)

        if options.overlap is not None and chunks:
            chunks = apply_token_overlap(
                chunks,
                overlap=options.overlap,
                max_chunk_size=max(1, options.max_chunk_size),
            )

        return _finalize_chunk_indexes(chunks)

    def stream(self, filepath: str, content: str, options: ChunkOptions) -> Iterator[Chunk]:
        """Yield base chunks lazily. ``total_chunks`` is always ``-1``.

        Token overlap (``options.overlap``) is not applied in streaming mode; use
        :meth:`chunk` when overlap is required.
        """
        for idx, chunk in enumerate(self._iter_base_chunks(filepath, content, options)):
            yield _with_unknown_total(chunk, idx)

    def _iter_base_chunks(
        self,
        filepath: str,
        content: str,
        options: ChunkOptions,
    ) -> Iterator[Chunk]:
        if not content.strip():
            return

        language = options.language or detect_language(filepath=filepath, content=content)
        parse_result = parse_code(content, language, filepath=filepath)

        entities = enrich_parent_links(extract_entities(content, language, parse_result.tree))
        entity_sweep = EntityRangeSweep(entities)
        scope_tree = build_scope_tree(entities)
        import_infos = build_import_infos(entities)
        sibling_index = build_sibling_index(scope_tree.all_entities)

        precomputed_text_index = options._precomputed_text_index
        if isinstance(precomputed_text_index, TextIndex):
            text_index = precomputed_text_index
        else:
            text_index = TextIndex(content)

        cumsum = options._precomputed_nws_cumsum
        if cumsum is None:
            cumsum = preprocess_nws_cumsum(content, backend=options.nws_backend)

        raw_bytes = text_index.raw_bytes

        budget = SourceBudget(
            content,
            text_index,
            make_size_counter(options.size_unit, options.tokenizer, cache_maxsize=0),
            size_unit=options.size_unit,
        )

        ast_nodes = _collect_ast_root_nodes(parse_result.tree)
        if ast_nodes:
            ast_nodes = _bind_leading_comments(
                ast_nodes,
                budget,
                options.max_chunk_size,
                options.overflow_policy == "split",
            )
            windows = assign_windows_for_nodes(
                ast_nodes,
                cumsum=cumsum,
                max_size=options.max_chunk_size,
                code=content,
                budget=budget,
                split_oversized=options.overflow_policy == "split",
            )
        else:
            candidate_ranges = _collect_candidate_ranges(
                entities, parse_result.tree, len(raw_bytes)
            )
            windows = assign_windows_for_ranges(
                candidate_ranges,
                cumsum=cumsum,
                max_size=options.max_chunk_size,
                code=content,
                budget=budget,
                split_oversized=options.overflow_policy == "split",
            )

        merged_windows = merge_adjacent_windows(
            windows,
            max_size=options.max_chunk_size,
            min_size=options.min_chunk_size,
            budget=budget,
        )
        merged_windows = _isolate_comment_groups(merged_windows, budget, options.max_chunk_size)

        chunk_ranges = _windows_to_contiguous_ranges(merged_windows, len(raw_bytes))
        chunk_ranges = _merge_whitespace_only_ranges(chunk_ranges, raw_bytes)
        token_counter = make_token_counter(options.tokenizer, chunk_size=options.max_chunk_size)

        previous_text = ""
        chunk_index = 0

        for start, end in chunk_ranges:
            if end <= start:
                continue

            text = raw_bytes[start:end].decode("utf-8", errors="replace")
            if not text.strip():
                continue

            byte_range = ByteRange(start=start, end=end)
            line_range = LineRange(
                start=text_index.line_for_byte(start),
                end=text_index.line_for_byte(max(start, end - 1)),
            )

            context = _build_context(
                filepath=filepath,
                language=language,
                chunk_range=byte_range,
                entities=entity_sweep.overlapping(byte_range),
                scope_tree=scope_tree,
                sibling_index=sibling_index,
                import_infos=import_infos,
                options=options,
                parse_errors=parse_result.errors,
            )
            context = replace(
                context,
                format_metadata={**context.format_metadata, "parser_backend": parse_result.backend},
            )

            overlap_text = build_line_overlap_text(previous_text, options.overlap_lines)
            contextualized_text = (
                text
                if options.context_mode == "none"
                else format_contextualized_text(text, context, overlap_text=overlap_text)
            )

            yield Chunk(
                text=text,
                contextualized_text=contextualized_text,
                byte_range=byte_range,
                line_range=line_range,
                index=chunk_index,
                total_chunks=-1,
                context=context,
                token_count=token_counter(text),
                char_count=len(text),
                nws_count=get_nws_count(cumsum, start, end),
            )

            previous_text = text
            chunk_index += 1


def _build_context(
    *,
    filepath: str,
    language: str,
    chunk_range: ByteRange,
    entities: list[EntityInfo],
    scope_tree: Any,
    sibling_index: SiblingIndex,
    import_infos: list[Any],
    options: ChunkOptions,
    parse_errors: list[str],
) -> ChunkContext:
    if options.context_mode == "none":
        return ChunkContext(
            filepath=filepath,
            language=language,  # type: ignore[arg-type]
            content_type=ContentType.CODE,
            parse_errors=list(parse_errors),
        )

    overlapping_entities = _entities_in_range(entities, chunk_range)
    scope = find_scope_chain(scope_tree, chunk_range)
    breadcrumb = [e.name for e in reversed(scope) if e.name]

    siblings = []
    if options.context_mode == "full" and options.sibling_detail != "none":
        siblings = detect_siblings_for_chunk(
            sibling_index,
            chunk_range,
            max_siblings=max(0, options.max_siblings),
        )
        if options.sibling_detail == "names":
            siblings = [replace(s, signature="") for s in siblings]

    imports = []
    if options.include_imports:
        if options.filter_imports:
            imports = filter_imports_for_chunk(
                import_infos, [e.signature for e in overlapping_entities if e.signature]
            )
        else:
            imports = import_infos

    if options.context_mode == "minimal":
        return ChunkContext(
            filepath=filepath,
            language=language,  # type: ignore[arg-type]
            content_type=ContentType.CODE,
            breadcrumb=breadcrumb,
            entities=[],
            siblings=[],
            imports=imports[:5],
            parse_errors=list(parse_errors),
        )

    return ChunkContext(
        filepath=filepath,
        language=language,  # type: ignore[arg-type]
        content_type=ContentType.CODE,
        scope=scope,
        breadcrumb=breadcrumb,
        entities=overlapping_entities,
        siblings=siblings,
        imports=imports,
        parse_errors=list(parse_errors),
    )


def _entities_in_range(entities: list[EntityInfo], chunk_range: ByteRange) -> list[EntityInfo]:
    out: list[EntityInfo] = []
    for entity in entities:
        br = entity.byte_range
        if br is None:
            continue
        if br.end <= chunk_range.start or br.start >= chunk_range.end:
            continue
        is_partial = br.start < chunk_range.start or br.end > chunk_range.end
        if is_partial:
            out.append(replace(entity, is_partial=True))
        else:
            out.append(entity)
    return out


def _collect_candidate_ranges(
    entities: list[EntityInfo],
    tree: Any | None,
    total_bytes: int,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []

    for entity in entities:
        if entity.byte_range is None:
            continue
        if entity.type.value in {"import", "export"}:
            continue
        start = entity.byte_range.start
        end = entity.byte_range.end
        if end > start:
            ranges.append((start, end))

    if not ranges and tree is not None:
        root = getattr(tree, "root_node", None)
        if root is not None:
            for child in getattr(root, "children", []) or []:
                start = int(getattr(child, "start_byte", 0))
                end = int(getattr(child, "end_byte", 0))
                if end > start:
                    ranges.append((start, end))

    if not ranges and total_bytes > 0:
        ranges.append((0, total_bytes))

    ranges.sort(key=lambda r: (r[0], r[1]))

    merged: list[tuple[int, int]] = []
    for start, end in ranges:
        start = max(0, min(start, total_bytes))
        end = max(0, min(end, total_bytes))
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    return merged


def _isolate_comment_groups(
    windows: list[list[ASTNodeWindowItem]], budget: SourceBudget, max_size: int
) -> list[list[ASTNodeWindowItem]]:
    """Keep fitting documented statements distinct in an oversized source.

    The whole-source fast path has no group markers and remains a single chunk.
    A tokenizer can make a subrange larger than its containing payload; retain
    the original valid window if any proposed structural piece would overflow.
    """
    isolated: list[list[ASTNodeWindowItem]] = []
    for window in windows:
        if not any(isinstance(item.node, _CommentGroup) for item in window):
            isolated.append(window)
            continue
        pieces: list[list[ASTNodeWindowItem]] = []
        pending: list[ASTNodeWindowItem] = []
        for item in window:
            if isinstance(item.node, _CommentGroup):
                if pending:
                    pieces.append(pending)
                    pending = []
                pieces.append([item])
            else:
                pending.append(item)
        if pending:
            pieces.append(pending)
        if all(budget.count(piece[0].start, piece[-1].end) <= max_size for piece in pieces):
            isolated.extend(pieces)
        else:
            isolated.append(window)
    return isolated


def _bind_leading_comments(
    nodes: list[Any], budget: SourceBudget, max_size: int, split_comments: bool = True
) -> list[Any]:
    """Keep an adjacent leading comment block with its fitting root statement.

    Source trivia belongs to the preceding sibling in measured windowing, so the
    fit check includes same-line trailing comments and the statement's trailing
    trivia. Original children remain available if a later full-source budget
    check still requires descent.
    """
    raw = budget.index.raw_bytes
    # Root offsets are queried repeatedly; scanning each entire source prefix
    # for a missing CR would otherwise make LF-only files quadratic.
    line_breaks = "\r\n\u2028\u2029"
    line_starts = [
        0,
        *(
            budget.index.byte_offset_for_char(offset + 1)
            for offset, char in enumerate(budget.text)
            if char in line_breaks
        ),
    ]
    output: list[Any] = []
    pending: list[Any] = []

    def adjacent(left: Any, right: Any) -> bool:
        gap = raw[int(left.end_byte) : int(right.start_byte)].decode("utf-8")
        newlines = sum(char in line_breaks for char in gap.replace("\r\n", "\n"))
        return not gap.strip() and newlines <= 1

    index = 0
    while index < len(nodes):
        node = nodes[index]
        start = int(node.start_byte)
        line_start = line_starts[bisect_right(line_starts, start) - 1]
        is_comment = "comment" in str(getattr(node, "type", "")).lower()
        leading_comment = is_comment and not raw[line_start:start].decode("utf-8").strip()
        if pending and not adjacent(pending[-1], node):
            output.extend(pending)
            pending = []
        if leading_comment:
            pending.append(node)
            index += 1
            continue
        if pending and not is_comment:
            group = [*pending, node]
            following = index + 1
            while following < len(nodes):
                trailing = nodes[following]
                gap = raw[int(group[-1].end_byte) : int(trailing.start_byte)].decode("utf-8")
                if (
                    "comment" not in str(getattr(trailing, "type", "")).lower()
                    or gap.strip()
                    or any(char in line_breaks for char in gap)
                ):
                    break
                group.append(trailing)
                following += 1
            owned_start = int(pending[0].start_byte) if output else 0
            owned_end = int(nodes[following].start_byte) if following < len(nodes) else len(raw)
            if budget.count(owned_start, owned_end) <= max_size:
                output.append(
                    _CommentGroup(
                        start=int(pending[0].start_byte),
                        end=int(group[-1].end_byte),
                        children=tuple(group),
                    )
                )
                pending = []
                index = following
                continue
            if split_comments:
                comment_start = int(pending[0].start_byte)
                comment_end = int(pending[-1].end_byte)
                comment_text = raw[comment_start:comment_end].decode("utf-8")
                # Preserve the final explanatory sentence with the documented
                # statement when the whole unit is too large. Both resulting
                # source payloads must independently fit the actual counter.
                cut = comment_start
                for sentence, _, _ in split_sentences(comment_text)[:-1]:
                    cut += len(sentence.encode("utf-8"))
                    if (
                        owned_start < cut < comment_end
                        and budget.count(owned_start, cut) <= max_size
                        and budget.count(cut, owned_end) <= max_size
                    ):
                        output.append(RangeNode(comment_start, cut))
                        tail = RangeNode(cut, comment_end)
                        output.append(
                            _CommentGroup(
                                start=cut,
                                end=int(group[-1].end_byte),
                                children=(tail, *group[len(pending) :]),
                            )
                        )
                        pending = []
                        index = following
                        break
                if not pending:
                    continue
            output.extend(pending)
            pending = []
        elif pending:
            output.extend(pending)
            pending = []
        output.append(node)
        index += 1
    output.extend(pending)
    return output


def _collect_ast_root_nodes(tree: Any | None) -> list[Any]:
    if tree is None:
        return []
    root = getattr(tree, "root_node", None)
    if root is None:
        return []

    candidates = list(getattr(root, "named_children", []) or [])
    if not candidates:
        candidates = list(getattr(root, "children", []) or [])

    out: list[Any] = []
    for node in candidates:
        start = int(getattr(node, "start_byte", 0))
        end = int(getattr(node, "end_byte", 0))
        if end > start:
            out.append(node)
    return out


def _windows_to_contiguous_ranges(
    windows: list[list[Any]], total_bytes: int
) -> list[tuple[int, int]]:
    if total_bytes <= 0:
        return []
    if not windows:
        return [(0, total_bytes)]

    sorted_windows = sorted(windows, key=lambda w: min(i.start for i in w))
    cut_points: list[int] = []
    for window in sorted_windows:
        end = max(item.end for item in window)
        cut_points.append(end)

    ranges: list[tuple[int, int]] = []
    cursor = 0
    for cut in cut_points:
        cut = max(cursor, min(cut, total_bytes))
        if cut > cursor:
            ranges.append((cursor, cut))
            cursor = cut
    if cursor < total_bytes:
        ranges.append((cursor, total_bytes))

    return ranges


def _merge_whitespace_only_ranges(
    ranges: list[tuple[int, int]],
    raw_bytes: bytes,
) -> list[tuple[int, int]]:
    if not ranges:
        return []

    merged: list[tuple[int, int]] = []
    pending_prefix: tuple[int, int] | None = None

    for start, end in ranges:
        segment = raw_bytes[start:end].decode("utf-8", errors="replace")
        if segment.strip():
            if pending_prefix is not None:
                start = pending_prefix[0]
                pending_prefix = None
            merged.append((start, end))
            continue

        if merged:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, end)
        else:
            pending_prefix = (start, end)

    if pending_prefix is not None and merged:
        first_start, first_end = merged[0]
        merged[0] = (pending_prefix[0], first_end)

    if not merged and ranges:
        return [ranges[0]]

    return merged


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
