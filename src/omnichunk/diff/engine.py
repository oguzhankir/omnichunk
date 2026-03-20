"""
Incremental chunk diff engine — stable ID set operations, O(N + M).
"""

from __future__ import annotations

from collections.abc import Sequence

from omnichunk.chunker import Chunker
from omnichunk.serialization import stable_chunk_id
from omnichunk.types import Chunk, ChunkDiff


def chunk_diff(
    filepath: str,
    new_content: str,
    *,
    previous_chunks: Sequence[Chunk],
    chunker: Chunker | None = None,
    **chunker_options: object,
) -> ChunkDiff:
    if chunker is None:
        chunker = Chunker(**chunker_options)

    new_chunks = chunker.chunk(filepath, new_content)

    prev_ids: set[str] = {stable_chunk_id(c) for c in previous_chunks}
    new_ids: set[str] = set()
    added: list[Chunk] = []
    unchanged: list[Chunk] = []

    for c in new_chunks:
        cid = stable_chunk_id(c)
        new_ids.add(cid)
        if cid in prev_ids:
            unchanged.append(c)
        else:
            added.append(c)

    removed_ids = sorted(prev_ids - new_ids)

    return ChunkDiff(added=added, removed_ids=removed_ids, unchanged=unchanged)
