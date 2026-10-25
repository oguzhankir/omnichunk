"""Offline durable delivery, restart recovery, ACL filtering and cited retrieval.

Run after ``pip install -e .``. Two SQLite files model the journal and a separate
retrieval backend. The small deterministic vectors exercise caching; retrieval
uses lexical matching and does not claim semantic quality.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from dataclasses import asdict
from pathlib import Path

from omnichunk import Chunker
from omnichunk.indexing import (
    DeliveryBatch,
    DeliveryReceipt,
    IndexJournal,
    IndexSource,
    RetryableSinkError,
)


class SQLiteProjection:
    """A minimal acknowledged sink, with application-owned authorization filtering."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.target_id = "sqlite-projection:" + str(path.resolve())
        self.lose_next_receipt = True
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE records (collection TEXT, id TEXT, record TEXT, "
                "PRIMARY KEY (collection, id))"
            )

    def apply(self, batch: DeliveryBatch) -> DeliveryReceipt:
        with sqlite3.connect(self.path) as connection:
            for record_id in batch.deletes:
                connection.execute(
                    "DELETE FROM records WHERE collection = ? AND id = ?",
                    (batch.collection, record_id),
                )
            for record in batch.upserts:
                connection.execute(
                    "INSERT INTO records VALUES (?, ?, ?) "
                    "ON CONFLICT(collection, id) DO UPDATE SET record = excluded.record",
                    (batch.collection, record.id, json.dumps(asdict(record))),
                )
        if self.lose_next_receipt:
            self.lose_next_receipt = False
            # Simulate a network interruption after the backend committed.
            raise RetryableSinkError("Backend committed, but its receipt was lost")
        return DeliveryReceipt(batch.idempotency_key, batch.operation_ids)

    def retrieve(self, query: str, *, principal: str, collection: str) -> list[dict]:
        # A service must resolve principal/collection from authenticated identity.
        # Filter before ranking so hidden records do not affect result counts.
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT record FROM records WHERE collection = ? AND EXISTS "
                "(SELECT 1 FROM json_each(record, '$.metadata.acl') WHERE value = ?)",
                (collection, principal),
            ).fetchall()
        terms = set(re.findall(r"\w+", query.casefold()))
        candidates = []
        for row in rows:
            record = json.loads(row[0])
            score = len(terms & set(re.findall(r"\w+", record["text"].casefold())))
            if score:
                candidates.append((score, record["id"], record))
        candidates.sort(key=lambda value: (-value[0], value[1]))
        return [value[2] for value in candidates[:3]]


def make_source(text: str, *, acl: list[str]) -> IndexSource:
    chunks = Chunker(max_chunk_size=128, context_mode="none", coverage_policy="lossless").chunk(
        "retention.txt", text, source_id="retention-policy"
    )
    assert chunks[0].source is not None
    return IndexSource("retention-policy", chunks[0].source.revision, tuple(chunks), {"acl": acl})


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="omnichunk-recovery-") as directory:
        root = Path(directory)
        sink = SQLiteProjection(root / "projection.sqlite")
        journal_path = root / "delivery.sqlite"
        source_text = "Customer backups expire after thirty days."
        document = make_source(source_text, acl=["support"])
        embedded = []

        def embed(texts):
            embedded.extend(texts)
            return [[float(len(text)), 1.0] for text in texts]

        with IndexJournal(journal_path) as journal:
            plan = journal.plan(
                [document],
                collection="policies",
                target_id=sink.target_id,
                model_revision="offline-demo-length-v1",
                scope="policy-documents",
                complete_scope=True,
            )
            print(f"Dry run: {len(plan.added_ids)} additions, {len(plan.removed_ids)} removals")
            assert journal.status(collection="policies").pending_plan_id is None
            journal.enqueue(plan)
            try:
                journal.deliver(sink, embed, collection="policies", batch_size=16)
            except RetryableSinkError as error:
                print(error)
            assert journal.status(collection="policies").pending_plan_id == plan.plan_id

        # Reopen the journal after interruption: delivery and vectors persist.
        with IndexJournal(journal_path) as journal:
            resumed = journal.deliver(sink, embed, collection="policies", batch_size=16)
            assert resumed.completed and len(embedded) == 1
            found = sink.retrieve("customer backups", principal="support", collection="policies")
            assert len(found) == 1 and found[0]["text"] == source_text
            assert not sink.retrieve("backups", principal="visitor", collection="policies")
            citation = found[0]["metadata"]["omnichunk"]
            start, end = citation["byte_range"]["start"], citation["byte_range"]["end"]
            assert source_text.encode("utf-8")[start:end].decode("utf-8") == citation["text"]
            assert found[0]["source_revision"] == document.revision
            print("Recovered context:", found[0]["text"])
            print(f"Citation: {document.source_id}@{document.revision}, bytes {start}:{end}")

            # Metadata changes are delivered without paying for another embedding.
            refresh = journal.plan(
                [make_source(source_text, acl=["legal"])],
                collection="policies",
                target_id=sink.target_id,
                model_revision="offline-demo-length-v1",
            )
            assert len(refresh.metadata_update_ids) == 1
            journal.enqueue(refresh)
            journal.deliver(sink, embed, collection="policies")
            assert len(embedded) == 1
            assert not sink.retrieve("backups", principal="support", collection="policies")
            assert sink.retrieve("backups", principal="legal", collection="policies")

            removal = journal.plan(
                [],
                collection="policies",
                target_id=sink.target_id,
                model_revision="offline-demo-length-v1",
                delete_sources=(document.source_id,),
            )
            journal.enqueue(removal)
            journal.deliver(sink, embed, collection="policies")
            assert not sink.retrieve("backups", principal="legal", collection="policies")
            assert journal.records(collection="policies") == ()
        print("Verified: durable replay, embedding reuse, ACL refresh and deletion.")


if __name__ == "__main__":
    main()
