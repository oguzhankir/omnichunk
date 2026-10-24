"""Offline retrieval with SQLite sync, source citations, edits and deletions.

Run after ``pip install -e .``. No model, API key or service is required. Lexical
ranking makes the lifecycle inspectable; it is not a semantic retrieval benchmark.
The in-memory projection is a demo, not durable delivery to an external database.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from omnichunk import Chunker, stable_chunk_id
from omnichunk.store import ChunkStore, SyncResult
from omnichunk.types import Chunk


def apply_sync(index: dict[str, Chunk], result: SyncResult) -> None:
    """Apply deletions before additions; refresh metadata on unchanged payloads."""
    for chunk_id in result.removed_chunk_ids:
        index.pop(chunk_id, None)
    for diff in result.diffs.values():
        # A vector backend would embed only `added`, which includes `updated`.
        # `unchanged` can carry new citation offsets without needing new vectors.
        for chunk in [*diff.added, *diff.unchanged]:
            index[stable_chunk_id(chunk)] = chunk


def retrieve(index: dict[str, Chunk], query: str, *, top_k: int = 3) -> list[Chunk]:
    """Small lexical baseline. Replace with your retriever in an application."""
    terms = set(re.findall(r"\w+", query.casefold()))
    ranked = []
    for chunk_id, chunk in index.items():
        words = set(re.findall(r"\w+", chunk.text.casefold()))
        score = len(terms & words)
        if score:
            ranked.append((score, chunk_id, chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [chunk for _, _, chunk in ranked[:top_k]]


def cited_context(chunks: list[Chunk], *, max_chars: int = 400) -> str:
    """Budget the complete rendered context, including citation labels."""
    context = ""
    for chunk in chunks:
        source = Path(chunk.context.filepath)
        raw = source.read_bytes()  # The demo corpus is UTF-8 text.
        start, end = chunk.byte_range.start, chunk.byte_range.end
        assert raw[start:end].decode("utf-8") == chunk.text
        label = f"[{source.name}, bytes {start}:{end}]"
        block = f"{label}\n{chunk.contextualized_text}"
        candidate = f"{context}\n\n{block}" if context else block
        if len(candidate) <= max_chars:
            context = candidate
    return context


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="omnichunk-rag-") as directory:
        workspace = Path(directory)
        corpus = workspace / "policies"
        corpus.mkdir()
        retention = corpus / "retention.txt"
        onboarding = corpus / "onboarding.txt"
        retention.write_text(
            "Customer backups expire after 30 days.\n\n"
            "Deletion requests are acknowledged within two business days.\n",
            encoding="utf-8",
        )
        onboarding.write_text(
            "New employees complete security training before accessing customer data.\n",
            encoding="utf-8",
        )
        chunker = Chunker(
            max_chunk_size=100,
            min_chunk_size=1,
            size_unit="chars",
            context_mode="none",
            coverage_policy="lossless",
        )
        index: dict[str, Chunk] = {}
        with ChunkStore(workspace / "index.sqlite", collection="policies") as store:
            first = store.index(corpus, glob="**/*.txt", chunker=chunker)
            apply_sync(index, first)
            assert first.files_updated == 2
            assert index

            query = "When do customer backups expire?"
            before = cited_context(retrieve(index, query))
            assert "30 days" in before and len(before) <= 400
            print("Initial retrieved context:\n" + before)

            # Apply a source edit and remove a source from the same scan scope.
            retention.write_text(
                retention.read_text(encoding="utf-8").replace("30 days", "45 days"),
                encoding="utf-8",
            )
            removed_ids = {
                chunk_id
                for chunk_id, chunk in index.items()
                if chunk.context.filepath == str(onboarding)
            }
            onboarding.unlink()
            changed = store.sync(corpus, glob="**/*.txt", chunker=chunker)
            apply_sync(index, changed)
            assert changed.files_updated == 1 and changed.files_deleted == 1
            assert removed_ids and removed_ids.isdisjoint(index)
            assert {stable_chunk_id(c) for c in store.query(str(retention))} == set(index)

            after = cited_context(retrieve(index, query))
            assert "45 days" in after and "30 days" not in after
            print("\nAfter editing retention and deleting onboarding:\n" + after)

            # Repeating the same scan does no new work.
            repeated = store.sync(corpus, glob="**/*.txt", chunker=chunker)
            apply_sync(index, repeated)
            assert repeated.files_skipped == 1 and not repeated.diffs
            assert not repeated.removed_chunk_ids

        # SQLite persists chunk records; rebuilding a retrieval projection does
        # not require re-chunking known source paths.
        with ChunkStore(workspace / "index.sqlite", collection="policies") as reopened:
            persisted = reopened.query(str(retention))
            assert {stable_chunk_id(c) for c in persisted} == set(index)
        print("\nVerified: citations, edit/delete sync, unchanged skip and persisted records.")


if __name__ == "__main__":
    main()
