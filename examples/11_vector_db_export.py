"""
Vector export shapes with placeholder vectors; no external writes or retrieval.
"""

from __future__ import annotations

from omnichunk import Chunker
from omnichunk.serialization import (
    chunks_to_pinecone_upsert_request,
    chunks_to_pinecone_vectors,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
    stable_chunk_id,
    weaviate_object_id,
)


def main() -> None:
    code = "def foo():\n    return 1\n" * 6
    chunker = Chunker(max_chunk_size=48, size_unit="chars")
    chunks = chunker.chunk("api.py", code)
    # Shape demonstration only. Embed each chunk.contextualized_text with your
    # configured model before uploading real records.
    emb = [[0.1, 0.2, 0.3] for _ in chunks]

    request = chunks_to_pinecone_upsert_request(chunks, emb, namespace="ns1")
    assert request["namespace"] == "ns1"
    assert "namespace" not in request["vectors"][0]
    # The SDK call is index.upsert(**request). Legacy row exports remain useful
    # for clients which build their own request envelopes.
    pine = chunks_to_pinecone_vectors(chunks, emb)
    pine_plain = chunks_to_pinecone_vectors(
        chunks, emb, namespace="", use_contextualized_text=False
    )
    assert pine_plain[0]["metadata"]["text"] == chunks[0].text
    print("Pinecone[0] keys:", sorted(pine[0].keys()))
    print("  id == stable_chunk_id:", pine[0]["id"] == stable_chunk_id(chunks[0]))

    wv = chunks_to_weaviate_objects(chunks, emb, class_name="MyDoc")
    assert wv[0]["id"] == weaviate_object_id(stable_chunk_id(chunks[0]))
    print("Weaviate[0] class:", wv[0]["class"])
    print("Weaviate delete ID:", weaviate_object_id(stable_chunk_id(chunks[0])))
    # These are portable dictionaries, not Python v4 DataObject instances.
    # Map id -> uuid, properties -> properties, vector -> vector for that SDK;
    # the collection name is selected on the client rather than on each object.

    sb = chunks_to_supabase_rows(chunks, emb)
    print("Supabase[0] keys:", sorted(sb[0].keys())[:8], "…")

    print("Export shapes only: configure the vendor schema/client before sending real embeddings.")


if __name__ == "__main__":
    main()
