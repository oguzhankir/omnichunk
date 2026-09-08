"""Shared source, overlap and measured-payload contracts for all public engines.

Parsing proposes source spans. Finalization scans them once, with logarithmic
boundary probes only for oversized spans. It retains one emitted chunk plus the
source index and an occurrence counter, rather than collecting chunk text.
"""

from __future__ import annotations

import hashlib
from bisect import bisect_left
from collections.abc import Iterable, Iterator
from dataclasses import replace
from typing import Any

from omnichunk.config import configuration_fingerprint
from omnichunk.context.format import format_contextualized_text
from omnichunk.protocols import SizeCounter
from omnichunk.sizing.counter import make_size_counter, make_token_counter
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkingError,
    ChunkOptions,
    EntityInfo,
    LineRange,
    SourceDescriptor,
)
from omnichunk.util.text_index import TextIndex
from omnichunk.windowing.overlap import build_line_overlap_text


def source_descriptor(
    filepath: str,
    index: TextIndex,
    options: ChunkOptions,
    *,
    format_name: str = "text",
    encoding: str = "utf-8",
    metadata: dict[str, Any] | None = None,
) -> SourceDescriptor:
    return SourceDescriptor(
        options.source_id or filepath,
        hashlib.sha256(index.raw_bytes).hexdigest(),
        encoding=encoding,
        format_name=format_name,
        normalization="extracted" if format_name != "text" else "none",
        metadata=metadata or {},
    )


def skipped_ranges(chunks: Iterable[Chunk], source_size: int) -> tuple[ByteRange, ...]:
    """Complement of source-span union; overlaps never inflate coverage."""
    cursor = 0
    missing = []
    for c in sorted(chunks, key=lambda c: c.byte_range.start):
        if c.byte_range.start > cursor:
            missing.append(ByteRange(cursor, c.byte_range.start))
        cursor = max(cursor, c.byte_range.end)
    if cursor < source_size:
        missing.append(ByteRange(cursor, source_size))
    return tuple(missing)


def _entities(entities: list[EntityInfo], start: int, end: int) -> list[EntityInfo]:
    return [
        replace(e, is_partial=e.is_partial or e.byte_range.start < start or e.byte_range.end > end)
        if e.byte_range is not None
        else e
        for e in entities
        if e.byte_range is None or (e.byte_range.start < end and e.byte_range.end > start)
    ]


def _fit_end(text: str, start: int, end: int, limit: int, count: SizeCounter) -> int:
    """Find a verified fitting Unicode boundary; no tokenizer monotonicity promise."""
    lo, hi, best = start + 1, end, start
    while lo <= hi:
        mid = (lo + hi) // 2
        if count(text[start:mid]) <= limit:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    if best == start:
        # Token counts can fall when another character completes a token.
        # A failed binary search is not proof that no prefix fits.
        for candidate in range(start + 1, end + 1):
            if count(text[start:candidate]) <= limit:
                return candidate
    return best


def finalize_chunks(
    filepath: str,
    content: str,
    proposed: Iterable[Chunk],
    options: ChunkOptions,
    *,
    index: TextIndex | None = None,
    source: SourceDescriptor | None = None,
    fingerprint: str | None = None,
) -> Iterator[Chunk]:
    index = index or TextIndex(content)
    source = source or source_descriptor(filepath, index, options)
    raw = index.raw_bytes
    # Reuse the existing UTF-8 index rather than encoding each probe.
    char_offsets = index._char_to_byte
    size = make_size_counter(options.size_unit, options.tokenizer)
    tokens = make_token_counter(options.tokenizer)
    fingerprint = fingerprint or configuration_fingerprint(options)
    occurrences: dict[str, int] = {}
    previous: Chunk | None = None
    emitted = 0
    consumed = 0
    limit = options.max_chunk_size

    def emit(candidate: Chunk, begin: int, finish: int) -> Iterator[Chunk]:
        nonlocal previous, emitted
        start = bisect_left(char_offsets, begin)
        stop = bisect_left(char_offsets, finish)
        if char_offsets[start] != begin or char_offsets[stop] != finish:
            raise ChunkingError("Engine emitted a range inside a UTF-8 character")
        fresh_start = start
        if previous is not None and previous.byte_range.end == begin:
            prior_start = bisect_left(char_offsets, previous.byte_range.start)
            if options.overlap:
                amount = (
                    int(options.overlap * limit)
                    if isinstance(options.overlap, float)
                    else options.overlap
                )
                left, right = prior_start, start
                while left < right:
                    mid = (left + right) // 2
                    if size(content[mid:start]) <= amount:
                        right = mid
                    else:
                        left = mid + 1
                start = left
        while start < stop:
            text = content[start:stop]
            if options.coverage_policy == "retrieval" and not text.strip():
                return
            end = stop
            overflow = size(text) > limit
            if overflow and options.overflow_policy == "error":
                raise ChunkingError(
                    f"Chunk exceeds {limit} {options.size_unit}; choose split or preserve"
                )
            if overflow and options.overflow_policy == "split":
                end = _fit_end(content, start, stop, limit, size)
                if end <= start or end <= fresh_start:
                    # Avoid emitting a chunk consisting solely of requested overlap.
                    start = max(start, fresh_start)
                    end = _fit_end(content, start, stop, limit, size)
                if end <= start:
                    raise ChunkingError("A single Unicode character cannot fit the selected budget")
                verified_end = end
                # A small complete declaration (including its decorator) wins
                # over an arbitrary line boundary through that declaration.
                containing = [
                    e.byte_range.start
                    for e in candidate.context.entities
                    if e.byte_range is not None
                    and char_offsets[start]
                    < e.byte_range.start
                    < char_offsets[end]
                    < e.byte_range.end
                    and size(raw[e.byte_range.start : e.byte_range.end].decode("utf-8")) <= limit
                ]
                if containing:
                    end = bisect_left(char_offsets, min(containing))
                boundary = content.rfind("\n", start, end)
                if boundary + 1 > max(start, fresh_start):
                    end = boundary + 1
                elif not containing:
                    for pos in range(end - 1, max(start, fresh_start), -1):
                        if content[pos].isspace() or content[pos] in ",;)]}":
                            end = pos + 1
                            break
                # Shorter strings can have more tokens: boundary preferences
                # must not replace a measured fitting prefix with an overflow.
                if end <= fresh_start or size(content[start:end]) > limit:
                    end = verified_end
                text = content[start:end]
            if not text.strip() and options.coverage_policy == "retrieval":
                start = end
                fresh_start = end
                continue
            begin_b, end_b = char_offsets[start], char_offsets[end]
            context = replace(
                candidate.context, entities=_entities(candidate.context.entities, begin_b, end_b)
            )
            overlap_text = (
                build_line_overlap_text(previous.text, options.overlap_lines) if previous else ""
            )
            rendered = (
                text
                if options.context_mode == "none"
                else format_contextualized_text(text, context, overlap_text)
            )
            metadata = dict(candidate.metadata)
            if size(rendered) > limit and options.overflow_policy != "preserve":
                if options.context_overflow == "error" and rendered != text:
                    raise ChunkingError(
                        'Context exceeds payload budget; use context_overflow="omit" '
                        "or increase size"
                    )
                metadata["context_omitted"] = rendered != text
                rendered = text
            measured = size(rendered)
            if measured > limit and options.overflow_policy != "preserve":
                raise ChunkingError("Final payload exceeds the configured budget")
            digest = hashlib.sha256(raw[begin_b:end_b]).hexdigest()
            occurrence = occurrences.get(digest, 0)
            occurrences[digest] = occurrence + 1
            metadata["budget"] = {
                "unit": options.size_unit,
                "limit": limit,
                "size": measured,
                "raw_size": size(text),
                "overflow": max(0, measured - limit),
                "policy": options.overflow_policy,
                "token_accuracy": "estimated"
                if options.tokenizer in (None, "approximate")
                else "exact",
                "rendered_token_count": tokens(rendered),
            }
            if measured > limit:
                metadata["overflow_reason"] = "structure-preserving policy"
            chunk = replace(
                candidate,
                text=text,
                contextualized_text=rendered,
                byte_range=ByteRange(begin_b, end_b),
                line_range=LineRange(
                    index.line_for_byte(begin_b), index.line_for_byte(max(begin_b, end_b - 1))
                ),
                context=context,
                index=emitted,
                total_chunks=-1,
                char_count=len(text),
                token_count=tokens(text),
                nws_count=sum(not ch.isspace() for ch in text),
                source=source,
                config_fingerprint=fingerprint,
                occurrence=occurrence,
                metadata=metadata,
            )
            previous = chunk
            emitted += 1
            yield chunk
            fresh_start = end
            if options.overlap and end < stop:
                amount = (
                    int(options.overlap * limit)
                    if isinstance(options.overlap, float)
                    else options.overlap
                )
                left, right = start + 1, end
                while left < right:
                    mid = (left + right) // 2
                    if size(content[mid:end]) <= amount:
                        right = mid
                    else:
                        left = mid + 1
                start = left
            else:
                start = end

    for candidate in proposed:
        begin, finish = candidate.byte_range.start, candidate.byte_range.end
        if begin < consumed or finish < begin or finish > len(raw):
            raise ChunkingError("Engine emitted unsorted or invalid source ranges")
        if raw[begin:finish].decode("utf-8") != candidate.text:
            raise ChunkingError("Engine text does not match its canonical source range")
        if begin > consumed and options.coverage_policy == "lossless":
            yield from emit(candidate, consumed, begin)
        yield from emit(candidate, begin, finish)
        consumed = finish
    if consumed < len(raw) and options.coverage_policy == "lossless":
        context = ChunkContext(filepath=filepath)
        filler = Chunk("", "", ByteRange(0, 0), LineRange(0, 0), 0, -1, context)
        yield from emit(filler, consumed, len(raw))
