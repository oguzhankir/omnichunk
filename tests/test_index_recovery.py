"""Recovery contracts exercised through public APIs and a durable remote projection."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest

from omnichunk import Chunker
from omnichunk.indexing import (
    AcknowledgementError,
    DeliveryBatch,
    DeliveryReceipt,
    IndexConflictError,
    IndexJournal,
    IndexSource,
    PermanentSinkError,
    RetryableSinkError,
)


class DurableSink:
    """An independent SQLite database models acknowledged external side effects."""

    target_id = "durable-test-projection-v1"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS records "
                "(collection TEXT, id TEXT, record TEXT, PRIMARY KEY(collection, id))"
            )
            connection.execute("CREATE TABLE IF NOT EXISTS calls (key TEXT)")

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
                    (batch.collection, record.id, json.dumps(asdict(record), sort_keys=True)),
                )
            connection.execute("INSERT INTO calls VALUES (?)", (batch.idempotency_key,))
        return DeliveryReceipt(batch.idempotency_key, batch.operation_ids)

    def snapshot(self, collection: str = "default") -> dict[str, dict]:
        with sqlite3.connect(self.path) as connection:
            return {
                row[0]: json.loads(row[1])
                for row in connection.execute(
                    "SELECT id, record FROM records WHERE collection = ?", (collection,)
                )
            }


class CrashAfterCommitSink(DurableSink):
    def apply(self, batch: DeliveryBatch) -> DeliveryReceipt:
        super().apply(batch)
        os._exit(73)


class GatedSink(DurableSink):
    def __init__(self, path: str, entered: str, release: str) -> None:
        super().__init__(path)
        self.entered, self.release = Path(entered), Path(release)

    def apply(self, batch: DeliveryBatch) -> DeliveryReceipt:
        receipt = super().apply(batch)
        self.entered.touch()
        wait_for_file(self.release)
        return receipt


def wait_for_file(path: Path) -> None:
    deadline = time.monotonic() + 15
    while not path.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Worker did not signal {path.name}")
        time.sleep(0.01)


def embed(texts: list[str]) -> list[list[float]]:
    return [[float(len(text)), float(sum(map(ord, text)) % 97)] for text in texts]


def source(source_id: str, text: str, *, metadata: dict | None = None) -> IndexSource:
    chunks = Chunker(
        max_chunk_size=100,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk(source_id + ".txt", text, source_id=source_id)
    assert chunks and chunks[0].source is not None
    return IndexSource(source_id, chunks[0].source.revision, tuple(chunks), metadata or {})


def enqueue(journal: IndexJournal, sink: DurableSink, sources, **kwargs):
    plan = journal.plan(sources, target_id=sink.target_id, model_revision="test-model-v1", **kwargs)
    journal.enqueue(plan)
    return plan


def test_process_crash_after_remote_commit_replays_without_reembedding(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.db"
    sink = DurableSink(tmp_path / "remote.db")
    sources = [source("retention", "Backups expire after thirty days.")]
    with IndexJournal(journal_path) as journal:
        plan = enqueue(journal, sink, sources)

    child = """
import os, runpy, sys
from pathlib import Path
helpers = runpy.run_path(sys.argv[1])
def counted_embed(texts):
    with open(sys.argv[4], 'a', encoding='utf-8') as stream:
        stream.write(str(len(texts)) + '\\n')
        stream.flush()
        os.fsync(stream.fileno())
    return helpers['embed'](texts)
with helpers['IndexJournal'](sys.argv[2]) as journal:
    journal.deliver(helpers['CrashAfterCommitSink'](sys.argv[3]), counted_embed)
"""
    calls = tmp_path / "embed-calls.txt"
    process = subprocess.run(
        [sys.executable, "-c", child, __file__, str(journal_path), str(sink.path), str(calls)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 73, process.stdout + process.stderr
    assert calls.read_text(encoding="utf-8").splitlines() == ["1"]
    assert len(sink.snapshot()) == 1

    def already_embedded(_texts):
        pytest.fail("A vector committed before remote delivery must survive process death")

    with IndexJournal(journal_path) as journal:
        assert journal.status().pending_plan_id == plan.plan_id
        assert journal.records() == ()
        delivered = journal.deliver(sink, already_embedded)
        assert delivered.completed
        assert delivered.reused_embeddings == 1
        assert journal.status().pending_plan_id is None
        assert len(journal.records()) == 1

    clean_sink = DurableSink(tmp_path / "clean-remote.db")
    with IndexJournal(tmp_path / "clean-journal.db") as clean:
        enqueue(clean, clean_sink, sources)
        assert clean.deliver(clean_sink, embed).completed
    assert sink.snapshot() == clean_sink.snapshot()
    with sqlite3.connect(sink.path) as connection:
        applied_keys = [row[0] for row in connection.execute("SELECT key FROM calls")]
    assert applied_keys == [applied_keys[0], applied_keys[0]]


def test_scoped_cleanup_and_explicit_deletion_do_not_remove_other_collections(tmp_path: Path):
    sink = DurableSink(tmp_path / "remote.db")
    alpha, beta = source("alpha", "Alpha policy."), source("beta", "Beta policy.")
    with IndexJournal(tmp_path / "journal.db") as journal:
        enqueue(journal, sink, [alpha], scope="policies", complete_scope=True)
        journal.deliver(sink, embed)
        enqueue(journal, sink, [beta], scope="handbook", complete_scope=True)
        journal.deliver(sink, embed)
        enqueue(journal, sink, [alpha], collection="other", scope="policies", complete_scope=True)
        journal.deliver(sink, embed, collection="other")

        # An incomplete/partial view cannot claim missing sources were deleted.
        enqueue(journal, sink, [], scope="policies", complete_scope=False)
        journal.deliver(sink, embed)
        assert len(sink.snapshot()) == 2
        enqueue(journal, sink, [], scope="policies", complete_scope=True)
        journal.deliver(sink, embed)
        assert {record["source_id"] for record in sink.snapshot().values()} == {"beta"}
        assert {record["source_id"] for record in sink.snapshot("other").values()} == {"alpha"}
        enqueue(journal, sink, [], delete_sources=("beta",))
        journal.deliver(sink, embed)
        assert sink.snapshot() == {}
        assert len(sink.snapshot("other")) == 1


def test_failed_source_enumeration_cannot_publish_deletions(tmp_path: Path) -> None:
    sink = DurableSink(tmp_path / "remote.db")
    alpha, beta = source("alpha", "Alpha policy."), source("beta", "Beta policy.")
    with IndexJournal(tmp_path / "journal.db") as journal:
        enqueue(journal, sink, [alpha, beta], scope="policies", complete_scope=True)
        journal.deliver(sink, embed)
        before = journal.records()
        generation = journal.status().generation

        def failed_scan():
            yield alpha
            raise OSError("Source traversal failed")

        with pytest.raises(OSError, match="traversal failed"):
            journal.plan(
                failed_scan(),
                target_id=sink.target_id,
                model_revision="test-model-v1",
                scope="policies",
                complete_scope=True,
            )
        assert journal.status().generation == generation
        assert journal.status().pending_plan_id is None
        assert journal.records() == before
        assert len(sink.snapshot()) == 2


def test_shared_source_survives_until_its_last_scope_releases_it(tmp_path: Path) -> None:
    sink = DurableSink(tmp_path / "remote.db")
    document = source("shared", "Shared policy.")
    with IndexJournal(tmp_path / "journal.db") as journal:
        for scope in ("handbook", "policies"):
            enqueue(journal, sink, [document], scope=scope, complete_scope=True)
            journal.deliver(sink, embed)
        enqueue(journal, sink, [], scope="handbook", complete_scope=True)
        journal.deliver(sink, embed)
        assert len(sink.snapshot()) == 1
        enqueue(journal, sink, [], scope="policies", complete_scope=True)
        journal.deliver(sink, embed)
        assert sink.snapshot() == {}


def test_bounded_delivery_checkpoint_survives_reopening(tmp_path: Path) -> None:
    sink = DurableSink(tmp_path / "remote.db")
    journal_path = tmp_path / "journal.db"
    embedded = []

    def counted_embed(texts):
        embedded.extend(texts)
        return embed(texts)

    with IndexJournal(journal_path) as journal:
        enqueue(journal, sink, [source("alpha", "Alpha policy."), source("beta", "Beta policy.")])
        checkpoint = journal.deliver(sink, counted_embed, batch_size=1, max_batches=1)
        assert not checkpoint.completed
        assert checkpoint.acknowledged == checkpoint.pending == 1
        assert journal.status().acknowledged_operations == 1
        assert len(sink.snapshot()) == 1
        assert not journal.records()  # Only a complete generation becomes acknowledged state.
    with IndexJournal(journal_path) as journal:
        assert journal.status().acknowledged_operations == 1
        assert journal.deliver(sink, counted_embed, batch_size=1).completed
        assert len(journal.records()) == 2
    assert len(embedded) == len(set(embedded)) == 2
    assert len(sink.snapshot()) == 2


def test_metadata_refresh_reuses_vectors_and_model_change_reembeds(tmp_path: Path) -> None:
    sink = DurableSink(tmp_path / "remote.db")
    calls = []

    def counted_embed(texts):
        calls.extend(texts)
        return embed(texts)

    original = source("policy", "Retention lasts thirty days.", metadata={"acl": ["support"]})
    changed = source("policy", "Retention lasts thirty days.", metadata={"acl": ["legal"]})
    journal_path = tmp_path / "journal.db"
    with IndexJournal(journal_path) as journal:
        enqueue(journal, sink, [original])
        journal.deliver(sink, counted_embed)
    with IndexJournal(journal_path) as journal:
        refresh = enqueue(journal, sink, [changed])
        assert len(refresh.metadata_update_ids) == 1
        assert not refresh.embedding_invalidations
        journal.deliver(sink, counted_embed)
        assert len(calls) == 1
        plan = journal.plan([changed], target_id=sink.target_id, model_revision="test-model-v2")
        assert len(plan.embedding_invalidations) == 1
        journal.enqueue(plan)
        journal.deliver(sink, counted_embed)
        assert len(calls) == 2


@pytest.mark.parametrize("error_type", [RetryableSinkError, PermanentSinkError])
def test_failed_delivery_remains_pending_until_explicitly_recovered(tmp_path: Path, error_type):
    class FailingSink(DurableSink):
        def apply(self, batch):
            raise error_type("remote unavailable")

    sink = FailingSink(tmp_path / "remote.db")
    with IndexJournal(tmp_path / "journal.db") as journal:
        enqueue(journal, sink, [source("policy", "Retain documents.")])
        with pytest.raises(error_type, match="remote unavailable"):
            journal.deliver(sink, embed)
        status = journal.status()
        assert status.pending_plan_id is not None
        assert status.pending_operations == 1
        assert status.retryable is (error_type is RetryableSinkError)
        assert not journal.records()
        if error_type is PermanentSinkError:
            with pytest.raises(PermanentSinkError, match="retry_failed"):
                journal.deliver(DurableSink(sink.path), embed)
        recovered = journal.deliver(
            DurableSink(sink.path), embed, retry_failed=error_type is PermanentSinkError
        )
        assert recovered.completed
        assert len(sink.snapshot()) == 1


def test_partial_receipt_does_not_acknowledge_the_batch(tmp_path: Path) -> None:
    class PartialSink(DurableSink):
        def apply(self, batch):
            super().apply(batch)
            return DeliveryReceipt(batch.idempotency_key, batch.operation_ids[:1])

    sink = PartialSink(tmp_path / "remote.db")
    with IndexJournal(tmp_path / "journal.db") as journal:
        enqueue(journal, sink, [source("alpha", "Alpha policy."), source("beta", "Beta policy.")])
        with pytest.raises(AcknowledgementError, match="(?i)(receipt|acknowledg)"):
            journal.deliver(sink, embed, batch_size=2)
        assert journal.status().pending_operations == 2
        assert not journal.records()
        assert journal.deliver(DurableSink(sink.path), embed, retry_failed=True).completed
        assert len(sink.snapshot()) == 2


def test_stale_dry_run_cannot_replace_a_newer_generation(tmp_path: Path) -> None:
    sink = DurableSink(tmp_path / "remote.db")
    with IndexJournal(tmp_path / "journal.db") as journal:
        stale = journal.plan(
            [source("policy", "Old policy.")],
            target_id=sink.target_id,
            model_revision="test-model-v1",
        )
        enqueue(journal, sink, [source("policy", "Current policy.")])
        journal.deliver(sink, embed)
        with pytest.raises(IndexConflictError, match="(?i)(stale|generation)"):
            journal.enqueue(stale)
        assert journal.status().pending_plan_id is None
        assert {record["text"] for record in sink.snapshot().values()} == {"Current policy."}


def test_competing_processes_cannot_replay_old_writes_after_a_new_generation(tmp_path: Path):
    journal_path = tmp_path / "journal.db"
    sink = DurableSink(tmp_path / "remote.db")
    entered, release, started = (tmp_path / name for name in ("entered", "release", "started"))
    with IndexJournal(journal_path) as journal:
        enqueue(journal, sink, [source("policy", "Old policy.")])

    child = """
import runpy, sys
from pathlib import Path
helpers = runpy.run_path(sys.argv[1])
sink = (helpers['GatedSink'](sys.argv[3], sys.argv[5], sys.argv[6])
        if sys.argv[4] == 'gated' else helpers['DurableSink'](sys.argv[3]))
with helpers['IndexJournal'](sys.argv[2]) as journal:
    if sys.argv[4] != 'gated':
        Path(sys.argv[7]).touch()
    journal.deliver(sink, helpers['embed'], batch_size=1)
"""
    arguments = [
        sys.executable,
        "-c",
        child,
        __file__,
        str(journal_path),
        str(sink.path),
        "gated",
        str(entered),
        str(release),
        str(started),
    ]
    workers = []
    try:
        workers.append(subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        wait_for_file(entered)
        arguments[6] = "ordinary"
        workers.append(subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        wait_for_file(started)
        # The first worker has committed remote state but still owns the journal
        # write transaction. Another worker cannot acknowledge or supersede it.
        with (
            IndexJournal(journal_path) as journal,
            pytest.raises(IndexConflictError, match="pending"),
        ):
            journal.plan(
                [source("policy", "Current policy.")],
                target_id=sink.target_id,
                model_revision="test-model-v1",
            )
        release.touch()
        stdout, stderr = workers[0].communicate(timeout=20)
        assert workers[0].returncode == 0, stdout + stderr
        # The competing worker may still be waking up from its write-lock wait.
        # It must reselect pending work, rather than send a previously read batch.
        with IndexJournal(journal_path) as journal:
            enqueue(journal, sink, [source("policy", "Current policy.")])
            journal.deliver(sink, embed, batch_size=1)
        stdout, stderr = workers[1].communicate(timeout=20)
        assert workers[1].returncode == 0, stdout + stderr
    finally:
        release.touch()
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)
    assert {record["text"] for record in sink.snapshot().values()} == {"Current policy."}
    with IndexJournal(journal_path) as journal:
        assert journal.status().generation == 2
        assert journal.status().pending_plan_id is None
