"""Run with ``pip install -e '.[qdrant]'``; Qdrant local mode needs no server.

The two keyword features demonstrate persistence and ACL filtering, not semantic
retrieval quality. Replace ``embed`` and its model revision in an application.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

from qdrant_client import QdrantClient, models

from omnichunk import Chunker
from omnichunk.indexing import IndexJournal, IndexSource
from omnichunk.indexing.sinks import QdrantSink


def embed(texts: Sequence[str]) -> list[list[float]]:
    return [
        [float(text.lower().count("backup") + 1), float(text.lower().count("export") + 1)]
        for text in texts
    ]


def main() -> None:
    client = QdrantClient(":memory:")
    client.create_collection(
        "policies", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE)
    )
    sink = QdrantSink(
        client, target_id="demo-qdrant:policies", collection_name="policies", dimensions=2
    )
    chunks = Chunker(context_mode="none").chunk("backup.txt", "Backup retention is thirty days.")
    assert chunks[0].source is not None
    source = IndexSource(
        chunks[0].source.source_id, chunks[0].source.revision, tuple(chunks), {"acl": ["support"]}
    )
    with (
        TemporaryDirectory() as temporary,
        IndexJournal(Path(temporary) / "delivery.sqlite") as journal,
    ):
        plan = journal.plan(
            [source],
            collection="tenant-a",
            target_id=sink.target_id,
            model_revision="demo-keywords-v1",
        )
        print("Dry-run plan:", plan.to_json())
        journal.enqueue(plan)
        assert journal.deliver(sink, embed, collection="tenant-a", batch_size=16).completed

        # An application derives the requester group from its authenticated
        # identity. Both collection and ACL checks belong in the database query.
        authorized = models.Filter(
            must=[
                models.FieldCondition(key="collection", match=models.MatchValue(value="tenant-a")),
                models.FieldCondition(key="metadata.acl", match=models.MatchValue(value="support")),
            ]
        )
        results = client.query_points(
            "policies", query=embed(["backup"])[0], query_filter=authorized
        ).points
        assert len(results) == 1
        assert results[0].payload is not None
        print("Authorized result:", results[0].payload["text"])
        print("Canonical citation:", results[0].payload["metadata"]["omnichunk"]["byte_range"])

        deletion = journal.plan(
            [],
            collection="tenant-a",
            target_id=sink.target_id,
            model_revision="demo-keywords-v1",
            delete_sources=[source.source_id],
        )
        journal.enqueue(deletion)
        assert journal.deliver(sink, collection="tenant-a").completed
        assert client.count("policies").count == 0
    client.close()


if __name__ == "__main__":
    main()
