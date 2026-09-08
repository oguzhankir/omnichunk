"""
Incremental chunk diff engine — stable ID set operations, O(N + M).
"""

from __future__ import annotations

from collections.abc import Sequence

from omnichunk.chunker import Chunker
from omnichunk.serialization import chunk_embedding_fingerprint, stable_chunk_id
from omnichunk.types import Chunk, ChunkDiff


def chunk_diff(
    filepath: str,
    new_content: str,
    *,
    previous_chunks: Sequence[Chunk],
    chunker: Chunker | None = None,
    **chunker_options: object,
) -> ChunkDiff:
    if chunker is not None and chunker_options:
        raise ValueError("Pass a configured chunker or chunker_options, not both")
    if chunker is None:
        chunker = Chunker(**chunker_options)

    new_chunks = chunker.chunk(filepath, new_content)

    return diff_chunks(previous_chunks, new_chunks)


def diff_chunks(previous: Sequence[Chunk], new: Sequence[Chunk]) -> ChunkDiff:
    """Compare occurrence identity and payload/configuration in O(N + M).

    ``updated`` is an advisory subset of ``added`` for same-ID payload changes.
    For legacy consumers, updates also appear in ``removed_ids``; apply deletes
    before upserts. Moved unchanged payloads remain ``unchanged`` and carry their
    new location metadata. Duplicate occurrence IDs are rejected, never dropped.
    """
    prev = {stable_chunk_id(c): c for c in previous}
    if len(prev) != len(previous):
        raise ValueError("Previous chunks contain duplicate occurrence IDs")
    new_ids: set[str] = set()
    added: list[Chunk] = []
    unchanged: list[Chunk] = []
    updated: list[Chunk] = []
    invalidated: set[str] = set()

    for c in new:
        cid = stable_chunk_id(c)
        if cid in new_ids:
            raise ValueError("New chunks contain duplicate occurrence IDs")
        new_ids.add(cid)
        old = prev.get(cid)
        if old is not None and chunk_embedding_fingerprint(old) == chunk_embedding_fingerprint(c):
            unchanged.append(c)
        else:
            added.append(c)
            if old is not None:
                updated.append(c)
                invalidated.add(cid)

    removed_ids = sorted((set(prev) - new_ids) | invalidated)

    return ChunkDiff(added=added, removed_ids=removed_ids, unchanged=unchanged, updated=updated)
