"""
Incremental chunk_diff across three synthetic versions; stable_chunk_id stability.
"""

from __future__ import annotations

import sys
from pathlib import Path

repo_src = Path(__file__).resolve().parents[1] / "src"
if repo_src.exists():
    sys.path.insert(0, str(repo_src))

from omnichunk import Chunker, chunk_diff, stable_chunk_id


def main() -> None:
    v1 = ("hello world\n") * 10
    v2 = v1 + ("append block\n") * 3
    v3 = v2.replace("hello", "hi").replace("append block\n", "")

    chunker = Chunker(max_chunk_size=120, size_unit="chars", min_chunk_size=1)
    c1 = chunker.chunk("doc.txt", v1)

    d12 = chunk_diff("doc.txt", v2, previous_chunks=c1, chunker=chunker)
    print("v1 -> v2")
    print(f"  added={d12.total_added} removed={d12.total_removed} unchanged={d12.total_unchanged}")
    c2 = chunker.chunk("doc.txt", v2)

    d23 = chunk_diff("doc.txt", v3, previous_chunks=c2, chunker=chunker)
    print("v2 -> v3")
    print(f"  added={d23.total_added} removed={d23.total_removed} unchanged={d23.total_unchanged}")

    # Vector DB workflow: upsert added, delete removed_ids, skip unchanged embeddings
    print("workflow: upsert diff.added, delete diff.removed_ids, skip re-embed for diff.unchanged")

    ids_a = [stable_chunk_id(x) for x in c1]
    ids_b = [stable_chunk_id(x) for x in c1]
    assert ids_a == ids_b
    print("stable_chunk_id deterministic for same chunks:", ids_a[0][:16] + "…")

    # Append-only transition (prefix chunk ID preserved when sizing matches prefix length)
    base = ("hello world\n") * 10
    new = base + ("goodbye\n") * 5
    chunker2 = Chunker(max_chunk_size=120, size_unit="chars", min_chunk_size=1)
    prev = chunker2.chunk("append.txt", base)
    d_app = chunk_diff("append.txt", new, previous_chunks=prev, chunker=chunker2)
    print("append-only (illustrative):")
    print(f"  added={d_app.total_added} removed={d_app.total_removed} unchanged={d_app.total_unchanged}")


if __name__ == "__main__":
    main()
