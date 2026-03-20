"""
Vector export adapters: Pinecone / Weaviate / Supabase shapes; stable_chunk_id vs row ids.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Prefer local repo code when running from a checkout.
for candidate in (Path.cwd() / "src", Path(__file__).resolve().parents[1] / "src"):
    if candidate.exists():
        sys.path.insert(0, str(candidate))
        break

from omnichunk import Chunker
from omnichunk.serialization import (
    chunks_to_pinecone_vectors,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
    stable_chunk_id,
)


def main() -> None:
    code = "def foo():\n    return 1\n" * 6
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    chunks = chunker.chunk("api.py", code)
    emb = [[0.1, 0.2, 0.3] for _ in chunks]

    pine = chunks_to_pinecone_vectors(chunks, emb, namespace="ns1")
    pine_plain = chunks_to_pinecone_vectors(chunks, emb, namespace="", use_contextualized_text=False)
    print("Pinecone[0] keys:", sorted(pine[0].keys()))
    print("  id == stable_chunk_id:", pine[0]["id"] == stable_chunk_id(chunks[0]))

    wv = chunks_to_weaviate_objects(chunks, emb, class_name="MyDoc")
    print("Weaviate[0] class:", wv[0]["class"])

    sb = chunks_to_supabase_rows(chunks, emb)
    print("Supabase[0] keys:", sorted(sb[0].keys())[:8], "…")

    print("Upsert workflow: batch-upload vectors with these dict shapes; no client in omnichunk.")


if __name__ == "__main__":
    main()
