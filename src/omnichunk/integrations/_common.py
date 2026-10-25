"""Shared source identity and metadata rules for native framework adapters."""

from __future__ import annotations

import hashlib
from bisect import bisect_left
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from omnichunk import Chunker
from omnichunk.serialization import chunk_to_dict, stable_chunk_id
from omnichunk.types import Chunk
from omnichunk.util.text_index import TextIndex


@dataclass(frozen=True)
class FrameworkChunk:
    chunk: Chunk
    node_id: str
    metadata: dict[str, Any]
    char_start: int
    char_end: int
    parent_id: str | None
    children: tuple[str, ...]
    level: int


def split_source(
    text: str,
    metadata: dict[str, Any],
    native_id: str | None,
    *,
    options: dict[str, Any],
    filepath: str,
    levels: list[int] | None,
) -> list[FrameworkChunk]:
    if "omnichunk" in metadata:
        raise ValueError("Reserved 'omnichunk' metadata: input may already be chunked")
    path = metadata.get("filepath", filepath)
    if not isinstance(path, str) or not path:
        raise ValueError("filepath must be a nonempty string")
    source_id = metadata.get("source_id", native_id or metadata.get("source"))
    if source_id is None:
        source_id = (
            metadata.get("filepath") or "inline:" + hashlib.sha256(text.encode()).hexdigest()
        )
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("Source identity must be a nonempty string")
    if "source_id" in options:
        raise ValueError("Set source_id on each document, not shared adapter options")
    chunker = Chunker(**options)
    tree = (
        chunker.hierarchical_chunk(path, text, levels=levels, source_id=source_id)
        if levels is not None
        else None
    )
    chunks = (
        [node.chunk for node in tree.nodes]
        if tree is not None
        else chunker.chunk(path, text, source_id=source_id)
    )
    ids = [
        stable_chunk_id(chunk) + (f":level:{tree.nodes[i].level}" if tree else "")
        for i, chunk in enumerate(chunks)
    ]
    index = TextIndex(text)
    # Exact byte coordinates must be converted, not recovered with text.find:
    # repeated source text and derived context make substring searches ambiguous.
    result = []
    for i, chunk in enumerate(chunks):
        node = tree.nodes[i] if tree is not None else None
        parent = ids[node.parent_index] if node and node.parent_index is not None else None
        children = tuple(ids[j] for j in node.child_indices) if node else ()
        item_metadata = deepcopy(metadata)
        item_metadata["omnichunk"] = {
            "chunk": chunk_to_dict(chunk),
            "node_id": ids[i],
            "parent_id": parent,
            "child_ids": list(children),
            "level": node.level if node else 0,
        }
        result.append(
            FrameworkChunk(
                chunk,
                ids[i],
                item_metadata,
                bisect_left(index._char_to_byte, chunk.byte_range.start),
                bisect_left(index._char_to_byte, chunk.byte_range.end),
                parent,
                children,
                node.level if node else 0,
            )
        )
    return result
