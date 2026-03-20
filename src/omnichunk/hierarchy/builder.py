"""
Hierarchical chunk tree builder.

Level 0: chunk at ``levels[0]``. Each coarser level groups either consecutive
leaves (level 1) or consecutive nodes at the previous level (level 2+), so
parent byte ranges exactly span their children.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from omnichunk.chunker import Chunker
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ChunkNode,
    ChunkOptions,
    ChunkTree,
    EntityInfo,
    LineRange,
)


class _MutableNode:
    __slots__ = ("chunk", "level", "parent", "children", "leaf_lo", "leaf_hi")

    def __init__(
        self,
        chunk: Chunk,
        level: int,
        parent: int | None,
        children: list[int],
        leaf_lo: int,
        leaf_hi: int,
    ) -> None:
        self.chunk = chunk
        self.level = level
        self.parent = parent
        self.children = children
        self.leaf_lo = leaf_lo
        self.leaf_hi = leaf_hi


def _validate_levels(levels: Sequence[int]) -> tuple[int, ...]:
    lv = tuple(int(x) for x in levels)
    if len(lv) < 2:
        raise ValueError("hierarchical_chunk requires at least 2 levels")
    if any(x <= 0 for x in lv):
        raise ValueError("all levels must be > 0")
    if any(lv[i] > lv[i + 1] for i in range(len(lv) - 1)):
        raise ValueError("levels must be sorted in ascending order")
    return lv


def _chunk_at_level(
    filepath: str,
    content: str,
    max_size: int,
    size_unit: str,
    tokenizer: object,
    chunker_options: dict[str, object],
) -> list[Chunk]:
    opts = {k: v for k, v in chunker_options.items() if k in ChunkOptions.__dataclass_fields__}
    chunker = Chunker(
        max_chunk_size=max_size,
        min_chunk_size=max(1, max_size // 4),
        size_unit=size_unit,
        tokenizer=tokenizer,
        **opts,
    )
    return chunker.chunk(filepath, content)


def _merge_parent_context(children: list[Chunk], filepath: str) -> ChunkContext:
    first = children[0].context
    seen: dict[tuple[str, str], EntityInfo] = {}
    crumbs: list[str] = []
    for ch in children:
        crumbs.extend(ch.context.breadcrumb)
        for ent in ch.context.entities:
            seen[(ent.name, ent.type.value)] = ent
    return ChunkContext(
        filepath=filepath,
        language=first.language,
        content_type=first.content_type,
        scope=list(first.scope),
        breadcrumb=crumbs,
        entities=list(seen.values()),
        siblings=[],
        imports=list(first.imports) if first.imports else [],
        heading_hierarchy=list(first.heading_hierarchy),
        section_type=first.section_type,
        parse_errors=list(first.parse_errors),
    )


def _build_parent_chunk_from_leaf_slice(
    leaves: list[Chunk],
    leaf_lo: int,
    leaf_hi: int,
    content: str,
    filepath: str,
) -> Chunk:
    first_leaf = leaves[leaf_lo]
    last_leaf = leaves[leaf_hi]
    child_slice = leaves[leaf_lo : leaf_hi + 1]
    byte_start = first_leaf.byte_range.start
    byte_end = last_leaf.byte_range.end
    raw = content.encode("utf-8")
    text = raw[byte_start:byte_end].decode("utf-8")
    line_start = first_leaf.line_range.start
    line_end = last_leaf.line_range.end
    context = _merge_parent_context(child_slice, filepath)
    return Chunk(
        text=text,
        contextualized_text=text,
        byte_range=ByteRange(byte_start, byte_end),
        line_range=LineRange(line_start, max(line_start, line_end)),
        index=0,
        total_chunks=-1,
        context=context,
        token_count=sum(c.token_count for c in child_slice),
        char_count=sum(c.char_count for c in child_slice),
        nws_count=sum(c.nws_count for c in child_slice),
    )


def _leaf_metric(leaf: Chunk, size_unit: str) -> int:
    if size_unit == "chars":
        v = leaf.char_count
    elif size_unit == "tokens":
        v = leaf.token_count
    else:
        v = leaf.nws_count
    return max(1, int(v))


def _group_leaves_for_level(
    leaves: list[Chunk],
    max_size: int,
    size_unit: str,
    _tokenizer: object,
) -> list[list[int]]:
    groups: list[list[int]] = []
    current: list[int] = []
    current_size = 0
    for i, leaf in enumerate(leaves):
        leaf_size = _leaf_metric(leaf, size_unit)
        if current and current_size + leaf_size > max_size:
            groups.append(current)
            current = [i]
            current_size = leaf_size
        else:
            current.append(i)
            current_size += leaf_size
    if current:
        groups.append(current)
    return groups


def _node_metric(mnodes: list[_MutableNode], gi: int, size_unit: str) -> int:
    ch = mnodes[gi].chunk
    if size_unit == "chars":
        v = ch.char_count
    elif size_unit == "tokens":
        v = ch.token_count
    else:
        v = ch.nws_count
    return max(1, int(v))


def _group_prev_level_nodes(
    mnodes: list[_MutableNode],
    prev_indices: list[int],
    max_size: int,
    size_unit: str,
) -> list[list[int]]:
    groups: list[list[int]] = []
    current: list[int] = []
    current_size = 0
    for gi in prev_indices:
        sz = _node_metric(mnodes, gi, size_unit)
        if current and current_size + sz > max_size:
            groups.append(current)
            current = [gi]
            current_size = sz
        else:
            current.append(gi)
            current_size += sz
    if current:
        groups.append(current)
    return groups


def _finalize_chunk_indices(mnodes: list[_MutableNode]) -> None:
    max_level = max(m.level for m in mnodes) if mnodes else -1
    for level in range(max_level + 1):
        idxs = [i for i, m in enumerate(mnodes) if m.level == level]
        tot = len(idxs)
        for k, mi in enumerate(idxs):
            m = mnodes[mi]
            m.chunk = replace(m.chunk, index=k, total_chunks=tot)


def build_chunk_tree(
    filepath: str,
    content: str,
    *,
    levels: Sequence[int],
    size_unit: str = "chars",
    tokenizer: object = None,
    **chunker_options: object,
) -> ChunkTree:
    lv = _validate_levels(levels)
    L = len(lv)
    opts = dict(chunker_options)
    leaves = _chunk_at_level(filepath, content, lv[0], size_unit, tokenizer, opts)
    if not leaves:
        return ChunkTree(nodes=[], level_count=L)

    mnodes: list[_MutableNode] = []
    for i, leaf in enumerate(leaves):
        mnodes.append(
            _MutableNode(
                chunk=leaf,
                level=0,
                parent=None,
                children=[],
                leaf_lo=i,
                leaf_hi=i,
            )
        )

    prev_level_indices = list(range(len(mnodes)))

    for ell in range(1, L):
        max_sz = lv[ell]
        if ell == 1:
            groups = _group_leaves_for_level(leaves, max_sz, size_unit, tokenizer)
        else:
            groups = _group_prev_level_nodes(mnodes, prev_level_indices, max_sz, size_unit)

        new_level_indices: list[int] = []
        for group in groups:
            if ell == 1:
                child_global = tuple(sorted(prev_level_indices[j] for j in group))
                lo, hi = min(group), max(group)
            else:
                child_global = tuple(sorted(group))
                lo = min(mnodes[gi].leaf_lo for gi in group)
                hi = max(mnodes[gi].leaf_hi for gi in group)

            pchunk = _build_parent_chunk_from_leaf_slice(
                leaves, lo, hi, content, filepath
            )
            parent_idx = len(mnodes)
            mnodes.append(
                _MutableNode(
                    chunk=pchunk,
                    level=ell,
                    parent=None,
                    children=list(child_global),
                    leaf_lo=lo,
                    leaf_hi=hi,
                )
            )
            for ci in child_global:
                mnodes[ci].parent = parent_idx
            new_level_indices.append(parent_idx)

        prev_level_indices = new_level_indices

    _finalize_chunk_indices(mnodes)

    nodes = [
        ChunkNode(
            chunk=m.chunk,
            level=m.level,
            parent_index=m.parent,
            child_indices=tuple(sorted(m.children)),
        )
        for m in mnodes
    ]
    return ChunkTree(nodes=nodes, level_count=L)
