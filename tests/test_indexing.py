"""Plan integrity, embedding reuse and journal ownership contracts."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import replace

import pytest

from omnichunk import Chunker
from omnichunk.indexing import (
    DeliveryReceipt,
    IndexConflictError,
    IndexJournal,
    IndexPlan,
    IndexSource,
    JournalSchemaError,
)
from omnichunk.indexing.models import digest


def source(text="Access requires approval.", source_id="policy", metadata=None):
    chunks = tuple(
        Chunker(
            max_chunk_size=80, min_chunk_size=0, context_mode="none", source_id=source_id
        ).chunk("policy.txt", text)
    )
    return IndexSource(source_id, chunks[0].source.revision, chunks, metadata or {})


class Sink:
    target_id = "test:records"

    def __init__(self):
        self.rows = {}

    def apply(self, batch):
        for identifier in batch.deletes:
            self.rows.pop((batch.collection, identifier), None)
        for record in batch.upserts:
            self.rows[batch.collection, record.id] = record
        return DeliveryReceipt(batch.idempotency_key, batch.operation_ids)


def plan(journal, sources, **kwargs):
    return journal.plan(sources, target_id="test:records", model_revision="model-v1", **kwargs)


def embed(texts):
    return [[float(len(text)), 1.0] for text in texts]


def test_plan_is_dry_run_roundtrip_and_repeated_enqueue_is_idempotent(tmp_path):
    path = tmp_path / "journal.db"
    with IndexJournal(path) as journal:
        first = plan(journal, [source(metadata={"acl": ["support"]})])
        assert journal.status().generation == 0
        assert journal.records() == ()
        assert IndexPlan.from_json(first.to_json()) == first
        assert first.upserts[0].metadata["acl"] == ["support"]
        assert first.upserts[0].metadata["omnichunk"]["source"]["source_id"] == "policy"
        assert journal.enqueue(first) == journal.enqueue(first)
        result = journal.deliver(Sink(), embed)
        assert result.completed and result.acknowledged == 1
        assert journal.enqueue(first) == first.plan_id
    with IndexJournal(path) as journal:
        assert journal.status().generation == 1
        assert len(journal.records()) == 1


def test_metadata_updates_reuse_vectors_and_model_changes_reembed(tmp_path):
    calls = []

    def model(texts):
        calls.extend(texts)
        return embed(texts)

    with IndexJournal(tmp_path / "journal.db") as journal:
        sink = Sink()
        initial = source(metadata={"acl": ["alice"]})
        journal.enqueue(plan(journal, [initial]))
        journal.deliver(sink, model)
        update = plan(journal, [replace(initial, metadata={"acl": ["bob"]})])
        assert update.metadata_update_ids == initial_ids(update)
        assert not update.embedding_invalidations
        journal.enqueue(update)
        result = journal.deliver(sink, None)
        assert result.embedding_calls == 0 and result.reused_embeddings == 1
        assert len(calls) == 1
        again = journal.plan([initial], target_id=sink.target_id, model_revision="model-v2")
        assert again.embedding_invalidations == initial_ids(again)
        journal.enqueue(again)
        journal.deliver(sink, model)
        assert len(calls) == 2
        assert journal.prune_embeddings() == 1
        unchanged = journal.plan([initial], target_id=sink.target_id, model_revision="model-v2")
        assert unchanged.unchanged_ids and not unchanged.upserts
        journal.enqueue(unchanged)
        assert journal.status().pending_plan_id is None
        assert journal.deliver(sink).completed


def initial_ids(value):
    return tuple(record.id for record in value.upserts)


def test_scope_owners_and_explicit_deletion(tmp_path):
    with IndexJournal(tmp_path / "journal.db") as journal:
        sink = Sink()
        for scope in ("all", "team"):
            journal.enqueue(plan(journal, [source()], scope=scope, complete_scope=True))
            journal.deliver(sink, embed)
        journal.enqueue(plan(journal, [], scope="all", complete_scope=True))
        assert len(journal.records()) == 1
        deletion = plan(journal, [], scope="team", complete_scope=True)
        assert len(deletion.removed_ids) == 1
        journal.enqueue(deletion)
        journal.deliver(sink)
        assert journal.records() == () and sink.rows == {}
        assert journal.prune_embeddings() == 1
        journal.enqueue(plan(journal, [source()]))
        journal.deliver(sink, embed)
        journal.enqueue(plan(journal, [], delete_sources=["policy"]))
        journal.deliver(sink)
        assert not journal.records()


def test_pending_generation_target_and_policy_conflicts(tmp_path):
    with IndexJournal(tmp_path / "journal.db") as journal:
        first = plan(journal, [source(), source("Other content", "other")])
        stale = plan(journal, [source("Updated content")])
        journal.enqueue(first)
        with pytest.raises(IndexConflictError):
            journal.enqueue(stale)
        with pytest.raises(IndexConflictError):
            plan(journal, [source()])
        with pytest.raises(IndexConflictError):
            journal.prune_embeddings()
        wrong = Sink()
        wrong.target_id = "wrong"
        with pytest.raises(IndexConflictError):
            journal.deliver(wrong, embed)
        journal.deliver(Sink(), embed)
        with pytest.raises(IndexConflictError):
            journal.enqueue(stale)
        with pytest.raises(IndexConflictError):
            journal.plan([source()], target_id="wrong", model_revision="model-v1")
        with pytest.raises(IndexConflictError):
            journal.plan([source()], target_id="test:records", model_revision="model-v2")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"complete_scope": True},
        {"scope": ""},
        {"use_contextualized_text": 1},
        {"complete_scope": 1},
        {"collection": ""},
        {"preprocessing_revision": ""},
        {"delete_sources": "policy"},
    ],
)
def test_invalid_plan_policies(tmp_path, kwargs):
    with IndexJournal(tmp_path / "journal.db") as journal, pytest.raises(ValueError):
        plan(journal, [source()], **kwargs)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "wrong"),
        ("revision", "wrong"),
        ("metadata", {"omnichunk": {}}),
        ("metadata", {"x": float("nan")}),
        ("metadata", {1: "invalid"}),
        ("metadata", {"x": object()}),
    ],
)
def test_invalid_sources_are_rejected_before_enqueue(tmp_path, field, value):
    with IndexJournal(tmp_path / "journal.db") as journal:
        with pytest.raises(ValueError):
            plan(journal, [replace(source(), **{field: value})])
        assert journal.status().generation == 0


def test_duplicate_ids_ranges_and_incomplete_scans_are_rejected(tmp_path):
    item = source()
    with IndexJournal(tmp_path / "journal.db") as journal:
        for invalid in ([item, item], [replace(item, chunks=item.chunks * 2)]):
            with pytest.raises(ValueError):
                plan(journal, invalid)
        with pytest.raises(ValueError):
            plan(journal, [item], delete_sources=[item.source_id])
        chunk = item.chunks[0]
        with pytest.raises(ValueError):
            plan(journal, [replace(item, chunks=(replace(chunk, text="wrong"),))])
        with pytest.raises(ValueError):
            plan(
                journal, [replace(item, chunks=(chunk, replace(chunk, text="X" * len(chunk.text))))]
            )

        def broken():
            yield item
            raise OSError("scan interrupted")

        with pytest.raises(OSError):
            plan(journal, broken(), scope="scan", complete_scope=True)
        assert journal.status().generation == 0


def test_plan_mutation_unknown_fields_and_forged_provenance_fail(tmp_path):
    with IndexJournal(tmp_path / "journal.db") as journal:
        value = plan(journal, [source()])
        raw = json.loads(value.to_json())
        for key, bad in [
            ("base_generation", True),
            ("schema_version", 99),
            ("use_contextualized_text", 1),
            ("plan_id", "bad"),
            ("upserts", []),
            ("removed_ids", ["same", "same"]),
        ]:
            with pytest.raises(ValueError):
                IndexPlan.from_json(json.dumps({**raw, key: bad}))
        with pytest.raises(ValueError):
            IndexPlan.from_json(json.dumps({**raw, "unknown": 1}))
        with pytest.raises(ValueError):
            IndexPlan.from_json('{"schema_version":1,"schema_version":1}')
        value.upserts[0].metadata["acl"] = ["mutated"]
        with pytest.raises(ValueError, match="digest"):
            journal.enqueue(value)
        valid = plan(journal, [source()])
        forged = replace(
            valid, upserts=(replace(valid.upserts[0], id="forged"),), added_ids=("forged",)
        )
        forged = replace(forged, plan_id=digest(forged._body()))
        with pytest.raises(ValueError, match="provenance"):
            journal.enqueue(forged)
        assert journal.status().generation == 0


@pytest.mark.parametrize("version,tables", [(7, False), (0, True), (1, True)])
def test_unknown_database_is_unchanged(tmp_path, version, tables):
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    if tables:
        conn.execute("CREATE TABLE custom(value TEXT)")
    conn.execute(f"PRAGMA user_version={version}")
    conn.commit()
    conn.close()
    before = path.read_bytes()
    with pytest.raises(JournalSchemaError):
        IndexJournal(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"batch_size": 0},
        {"batch_size": True},
        {"max_batches": 0},
        {"max_batches": True},
        {"retry_failed": 1},
    ],
)
def test_delivery_limits_reject_invalid_values(tmp_path, kwargs):
    with IndexJournal(tmp_path / "journal.db") as journal, pytest.raises(ValueError):
        journal.deliver(Sink(), embed, **kwargs)


def test_local_completion_failure_rolls_back_ack_and_state_after_remote_success(
    tmp_path, monkeypatch
):
    sink = Sink()
    with IndexJournal(tmp_path / "journal.db") as journal:
        pending = plan(journal, [source()])
        journal.enqueue(pending)
        original = journal._finish

        def fail_after_writes(value):
            original(value)
            raise sqlite3.OperationalError("injected failure before commit")

        monkeypatch.setattr(journal, "_finish", fail_after_writes)
        with pytest.raises(sqlite3.OperationalError, match="injected"):
            journal.deliver(sink, embed)
        assert sink.rows  # The external side committed, so replay must be safe.
        assert journal.records() == ()
        status = journal.status()
        assert status.generation == 0
        assert status.acknowledged_operations == 0
        assert status.pending_operations == 1
        monkeypatch.setattr(journal, "_finish", original)
        result = journal.deliver(sink, None, retry_failed=True)
        assert result.completed and result.embedding_calls == 0
        assert len(sink.rows) == len(journal.records()) == 1


@pytest.mark.parametrize("keep_other_records", [False, True])
def test_imported_plan_rejects_conflicting_sibling_spans(tmp_path, keep_other_records):
    chunks = tuple(
        Chunker(
            max_chunk_size=8,
            min_chunk_size=0,
            context_mode="none",
            coverage_policy="lossless",
            source_id="policy",
        ).chunk("policy.txt", "alpha\n\nbravo\n\ncharlie")
    )
    item = IndexSource("policy", chunks[0].source.revision, chunks)
    with IndexJournal(tmp_path / "journal.db") as journal:
        if keep_other_records:
            journal.enqueue(plan(journal, [item]))
            journal.deliver(Sink(), embed)
            item = replace(
                item, chunks=(replace(chunks[0], metadata={"review": "updated"}), *chunks[1:])
            )
        value = plan(journal, [item])
        raw = json.loads(value.to_json())
        moving = raw["upserts"][0]
        other = next(chunk for chunk in chunks if chunk.text != moving["text"])
        bounds = moving["metadata"]["omnichunk"]["byte_range"]
        bounds["start"] = other.byte_range.start
        bounds["end"] = bounds["start"] + len(moving["text"].encode())
        raw["plan_id"] = digest({key: value for key, value in raw.items() if key != "plan_id"})
        imported = IndexPlan.from_json(json.dumps(raw))
        with pytest.raises(ValueError, match="Overlapping"):
            journal.enqueue(imported)
        assert journal.status().pending_plan_id is None


def test_imported_complete_scope_cannot_orphan_stale_source_records(tmp_path):
    first, second = source(), source("Other content", "other")
    with IndexJournal(tmp_path / "journal.db") as journal:
        sink = Sink()
        journal.enqueue(plan(journal, [first, second], scope="scan", complete_scope=True))
        journal.deliver(sink, embed)
        partial = plan(journal, [first], scope="scan")
        forged = replace(partial, complete_scope=True)
        forged = replace(forged, plan_id=digest(forged._body()))
        imported = IndexPlan.from_json(forged.to_json())
        with pytest.raises(ValueError, match="stale source deletions"):
            journal.enqueue(imported)
        assert len(journal.records()) == 2
        cleanup = plan(journal, [], scope="scan", complete_scope=True)
        assert set(cleanup.deleted_sources) == {"policy", "other"}
        journal.enqueue(cleanup)
        journal.deliver(sink)
        assert not journal.records() and not sink.rows


def test_concurrent_constructors_recheck_schema_after_acquiring_writer_lock(tmp_path, monkeypatch):
    """Force the first constructor's empty snapshot to overlap another initializer."""
    path = tmp_path / "fresh.db"
    first_inspected = threading.Event()
    release_first = threading.Event()
    second_at_commit = threading.Event()
    original_connect = sqlite3.connect
    failures = []
    opened = []

    class GatedConnection(sqlite3.Connection):
        paused = False
        creating = False

        def execute(self, sql, *args):
            second = threading.current_thread().name == "initializer-second"
            if second and sql.lstrip().startswith("CREATE TABLE"):
                self.creating = True
            if second and self.creating and sql == "COMMIT":
                # The fixed constructor holds its writer transaction here. Its
                # commit waits for the first constructor's read snapshot to end.
                second_at_commit.set()
            cursor = super().execute(sql, *args)
            if (
                threading.current_thread().name == "initializer-first"
                and not self.paused
                and sql.startswith("SELECT name FROM sqlite_master")
            ):
                self.paused = True
                rows = list(cursor)
                first_inspected.set()
                assert release_first.wait(10), "first constructor was not released"
                return rows
            return cursor

        def executescript(self, sql):
            # The old constructor committed its schema through executescript,
            # so release the first reader only after that competing commit.
            result = super().executescript(sql)
            if threading.current_thread().name == "initializer-second":
                second_at_commit.set()
            return result

    def connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=GatedConnection)

    def open_journal():
        try:
            with IndexJournal(path) as journal:
                opened.append(journal.status().generation)
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(sqlite3, "connect", connect)
    first = threading.Thread(target=open_journal, name="initializer-first")
    second = threading.Thread(target=open_journal, name="initializer-second")
    first.start()
    try:
        assert first_inspected.wait(10), "first constructor did not inspect the schema"
        second.start()
        assert second_at_commit.wait(10), "second constructor did not reach schema commit"
    finally:
        release_first.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)
    assert not first.is_alive() and not second.is_alive()
    assert failures == []
    assert opened == [0, 0]
    with IndexJournal(path) as journal:
        journal.enqueue(plan(journal, [source()]))
        assert journal.deliver(Sink(), embed).completed
