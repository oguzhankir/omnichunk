"""SQLite outbox with generation checks, durable vectors and explicit acknowledgements."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from omnichunk.serialization import chunk_from_dict, chunk_to_dict, stable_chunk_id

from .models import (
    AcknowledgementError,
    DeliveryBatch,
    DeliveryReceipt,
    DeliveryResult,
    IndexConflictError,
    IndexPlan,
    IndexRecord,
    IndexSink,
    IndexSource,
    IndexStatus,
    JournalSchemaError,
    PermanentSinkError,
    RetryableSinkError,
    VectorRecord,
    canonical_json,
    digest,
    embedding_key,
    json_value,
    name,
    vector_values,
)

_APPLICATION_ID = 0x4F43494A
_SCHEMA = f"""
CREATE TABLE collections (
 name TEXT PRIMARY KEY, target_id TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
 model TEXT NOT NULL, preprocessing TEXT NOT NULL, contextualized INTEGER NOT NULL,
 dimension INTEGER
);
CREATE TABLE sources (
 collection TEXT NOT NULL, source_id TEXT NOT NULL, revision TEXT NOT NULL,
 PRIMARY KEY(collection,source_id)
);
CREATE TABLE records (
 collection TEXT NOT NULL, id TEXT NOT NULL, source_id TEXT NOT NULL, body TEXT NOT NULL,
 PRIMARY KEY(collection,id)
);
CREATE INDEX records_source ON records(collection,source_id);
CREATE TABLE scopes (
 collection TEXT NOT NULL, scope TEXT NOT NULL, source_id TEXT NOT NULL,
 PRIMARY KEY(collection,scope,source_id)
);
CREATE TABLE plans (
 id TEXT PRIMARY KEY, collection TEXT NOT NULL, body TEXT NOT NULL,
 done INTEGER NOT NULL DEFAULT 0, error TEXT, retryable INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX pending_collection ON plans(collection) WHERE done = 0;
CREATE TABLE operations (
 plan_id TEXT NOT NULL, sequence INTEGER NOT NULL, operation_id TEXT NOT NULL,
 kind TEXT NOT NULL, record_id TEXT NOT NULL, body TEXT, acked INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(plan_id,sequence), UNIQUE(plan_id,operation_id)
);
CREATE TABLE embeddings (
 collection TEXT NOT NULL, fingerprint TEXT NOT NULL, vector TEXT NOT NULL,
 PRIMARY KEY(collection,fingerprint)
);
PRAGMA application_id = {_APPLICATION_ID};
PRAGMA user_version = 1;
"""


def _record(raw: str) -> IndexRecord:
    return IndexRecord(**json.loads(raw))


def _source_records(
    source: IndexSource, model: str, preprocessing: str, contextualized: bool
) -> tuple[IndexRecord, ...]:
    name(source.source_id, "source_id")
    name(source.revision, "revision")
    metadata = json_value(source.metadata)
    if not isinstance(metadata, dict):
        raise ValueError("Source metadata must be an object")
    records: list[IndexRecord] = []
    ids: set[str] = set()
    prior_end = 0
    prior_start = 0
    prior_text = b""
    for chunk in sorted(
        tuple(source.chunks), key=lambda item: (item.byte_range.start, item.byte_range.end)
    ):
        if chunk.source is not None and (
            chunk.source.source_id != source.source_id or chunk.source.revision != source.revision
        ):
            raise ValueError("Chunk source identity/revision differs from IndexSource")
        raw = chunk.text.encode("utf-8")
        start, end = chunk.byte_range.start, chunk.byte_range.end
        if type(start) is not int or type(end) is not int or start < 0 or end - start != len(raw):
            raise ValueError("Chunk byte range does not match its UTF-8 payload")
        if start < prior_end:
            overlap_end = min(prior_end, end)
            if (
                prior_text[start - prior_start : overlap_end - prior_start]
                != raw[: overlap_end - start]
            ):
                raise ValueError("Overlapping chunk source bytes disagree")
        if end > prior_end:
            prior_start, prior_end, prior_text = start, end, raw
        identifier = stable_chunk_id(chunk, filepath=source.source_id)
        if identifier in ids:
            raise ValueError("Duplicate chunk occurrence ID")
        ids.add(identifier)
        attrs = {**(chunk.source.metadata if chunk.source else {}), **chunk.metadata, **metadata}
        if "omnichunk" in attrs:
            raise ValueError("The metadata key 'omnichunk' is reserved for canonical chunk data")
        attrs["omnichunk"] = chunk_to_dict(chunk)
        payload = chunk.contextualized_text if contextualized else chunk.text
        records.append(
            IndexRecord(
                identifier,
                source.source_id,
                source.revision,
                payload,
                json_value(attrs),
                embedding_key(payload, model, preprocessing),
            )
        )
    return tuple(records)


class IndexJournal:
    """A separate delivery database; existing ChunkStore databases are untouched.

    A collection is bound to one caller-owned target identity and vector dimension.
    One pending plan serializes each collection. External calls occur under a
    SQLite write transaction; use independent connections for workers, never a
    reentrant journal callback. A sink must make every operation idempotent.
    """

    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path), isolation_level=None, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        try:
            # Existing journals can open while another worker delivers under a
            # write lock. Read all schema fields from one consistent snapshot.
            with self._transaction():
                fresh = self._check_schema()
            if fresh:
                with self._transaction(write=True):
                    # Another constructor may have initialized the database
                    # while this connection was waiting for the writer lock.
                    if self._check_schema():
                        for statement in _SCHEMA.split(";"):
                            if statement.strip():
                                # executescript() would commit our lock before
                                # executing the schema. These are static DDL and
                                # PRAGMA statements with no embedded semicolons.
                                self._conn.execute(statement)
        except BaseException:
            self._conn.close()
            raise

    def _check_schema(self) -> bool:
        """Inspect one transaction snapshot; return True for a fresh database."""
        tables = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        application = self._conn.execute("PRAGMA application_id").fetchone()[0]
        required = {
            "collections",
            "sources",
            "records",
            "scopes",
            "plans",
            "operations",
            "embeddings",
        }
        if not tables and version == 0 and application == 0:
            return True
        if version != 1 or application != _APPLICATION_ID or tables != required:
            raise JournalSchemaError(
                "Unsupported journal database; use a new journal and reconcile the target"
            )
        return False

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> IndexJournal:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[None]:
        self._conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def records(self, *, collection: str = "default") -> tuple[IndexRecord, ...]:
        """Return the last fully acknowledged generation, including source metadata."""
        return tuple(
            _record(row[0])
            for row in self._conn.execute(
                "SELECT body FROM records WHERE collection=? ORDER BY source_id,id",
                (name(collection, "collection"),),
            )
        )

    def status(self, *, collection: str = "default") -> IndexStatus:
        name(collection, "collection")
        with self._transaction():
            row = self._conn.execute(
                "SELECT generation FROM collections WHERE name=?", (collection,)
            ).fetchone()
            pending = self._conn.execute(
                "SELECT * FROM plans WHERE collection=? AND done=0", (collection,)
            ).fetchone()
            if pending is None:
                return IndexStatus(collection, row[0] if row else 0, None, 0, 0, None, True)
            count = self._conn.execute(
                "SELECT COUNT(*),COALESCE(SUM(acked),0) FROM operations WHERE plan_id=?",
                (pending["id"],),
            ).fetchone()
            return IndexStatus(
                collection,
                row[0],
                pending["id"],
                count[0] - count[1],
                count[1],
                pending["error"],
                bool(pending["retryable"]),
            )

    def plan(
        self,
        sources: Iterable[IndexSource],
        *,
        collection: str = "default",
        target_id: str,
        model_revision: str,
        preprocessing_revision: str = "identity-v1",
        use_contextualized_text: bool = True,
        scope: str | None = None,
        complete_scope: bool = False,
        delete_sources: Iterable[str] = (),
    ) -> IndexPlan:
        """Build a dry-run plan without committing source state or calling a model.

        Exhaust the supplied scan before planning. ``complete_scope`` removes only
        missing members of that named scope with no other scope owner. An explicit
        deletion removes all ownership. A failed/incomplete iterator cannot delete.
        """
        name(collection, "collection")
        name(target_id, "target_id")
        name(model_revision, "model_revision")
        name(preprocessing_revision, "preprocessing_revision")
        if type(use_contextualized_text) is not bool or type(complete_scope) is not bool:
            raise ValueError("Index policies must be booleans")
        if scope is not None:
            name(scope, "scope")
        elif complete_scope:
            raise ValueError("complete_scope requires an explicit scope")
        desired: dict[str, IndexSource] = {}
        new_records: dict[str, IndexRecord] = {}
        for source in sources:
            if not isinstance(source, IndexSource) or source.source_id in desired:
                raise ValueError("Expected unique IndexSource objects")
            rows = _source_records(
                source, model_revision, preprocessing_revision, use_contextualized_text
            )
            desired[source.source_id] = source
            for record in rows:
                if record.id in new_records:
                    raise ValueError("Duplicate record ID")
                new_records[record.id] = record
        if isinstance(delete_sources, (str, bytes)):
            raise ValueError("delete_sources must be an iterable of source IDs, not a string")
        deleted = {name(source_id, "deleted source_id") for source_id in delete_sources}
        if deleted & set(desired):
            raise ValueError("A source cannot be updated and deleted together")
        with self._transaction():
            current = self._conn.execute(
                "SELECT * FROM collections WHERE name=?", (collection,)
            ).fetchone()
            if self._conn.execute(
                "SELECT 1 FROM plans WHERE collection=? AND done=0", (collection,)
            ).fetchone():
                raise IndexConflictError(
                    "Deliver the pending collection plan before planning another"
                )
            if current and current["target_id"] != target_id:
                raise IndexConflictError("Collection is bound to a different target_id")
            previous = {row.id: row for row in self.records(collection=collection)}
            known_sources = {
                row[0]
                for row in self._conn.execute(
                    "SELECT source_id FROM sources WHERE collection=?", (collection,)
                )
            }
            if scope is not None and complete_scope:
                old_members = {
                    row[0]
                    for row in self._conn.execute(
                        "SELECT source_id FROM scopes WHERE collection=? AND scope=?",
                        (collection, scope),
                    )
                }
                other_members = {
                    row[0]
                    for row in self._conn.execute(
                        "SELECT source_id FROM scopes WHERE collection=? AND scope<>?",
                        (collection, scope),
                    )
                }
                deleted.update(old_members - set(desired) - other_members)
            if (
                current
                and (
                    current["model"],
                    current["preprocessing"],
                    bool(current["contextualized"]),
                )
                != (model_revision, preprocessing_revision, use_contextualized_text)
                and known_sources - set(desired) - deleted
            ):
                raise IndexConflictError(
                    "Policy changes require all existing sources or a new collection"
                )
            affected = set(desired) | deleted
            removed = tuple(
                sorted(
                    identifier
                    for identifier, record in previous.items()
                    if record.source_id in affected and identifier not in new_records
                )
            )
            added, metadata, invalidated, unchanged = [], [], [], []
            upserts = []
            for identifier, record in sorted(new_records.items()):
                old = previous.get(identifier)
                if old is None:
                    added.append(identifier)
                elif old.embedding_key != record.embedding_key:
                    invalidated.append(identifier)
                elif old != record:
                    metadata.append(identifier)
                else:
                    unchanged.append(identifier)
                    continue
                upserts.append(record)
            result = IndexPlan(
                collection,
                target_id,
                current["generation"] if current else 0,
                model_revision,
                preprocessing_revision,
                use_contextualized_text,
                tuple(sorted((key, value.revision) for key, value in desired.items())),
                tuple(sorted(deleted)),
                tuple(upserts),
                removed,
                tuple(added),
                tuple(metadata),
                tuple(invalidated),
                tuple(unchanged),
                scope,
                complete_scope,
                tuple(sorted(desired)) if scope else (),
            )
            result = replace(result, plan_id=digest(result._body()))
            return IndexPlan.from_json(result.to_json())

    def _validate_transition(self, plan: IndexPlan) -> None:
        """Validate source ownership and action semantics against the CAS snapshot."""
        previous = {record.id: record for record in self.records(collection=plan.collection)}
        sources = dict(plan.source_revisions)
        affected = set(sources) | set(plan.deleted_sources)
        upserts = {record.id: record for record in plan.upserts}
        removed = set(plan.removed_ids)
        unchanged = set(plan.unchanged_ids)
        expected_old = {key for key, record in previous.items() if record.source_id in affected}
        if expected_old != (removed | unchanged | (set(upserts) & set(previous))):
            raise ValueError("Plan does not account for every record in its affected sources")
        for identifier in removed | unchanged:
            if identifier not in previous or previous[identifier].source_id not in affected:
                raise ValueError("Plan record does not belong to an affected source")
        for identifier in unchanged:
            record = previous[identifier]
            if sources.get(
                record.source_id
            ) != record.source_revision or record.embedding_key != embedding_key(
                record.text, plan.model_revision, plan.preprocessing_revision
            ):
                raise ValueError("Unchanged record has stale source/model metadata")
        for record in (*plan.upserts, *(previous[key] for key in unchanged)):
            raw = record.metadata.get("omnichunk")
            if not isinstance(raw, dict):
                raise ValueError("Index record requires canonical chunk provenance")
            chunk = chunk_from_dict(raw)
            extra = {key: value for key, value in record.metadata.items() if key != "omnichunk"}
            expected = _source_records(
                IndexSource(record.source_id, record.source_revision, (chunk,), extra),
                plan.model_revision,
                plan.preprocessing_revision,
                plan.use_contextualized_text,
            )
            if expected != (record,):
                raise ValueError("Index record differs from its canonical chunk provenance")
            if record.id in unchanged:
                continue
            old = previous.get(record.id)
            if old is not None and old.source_id != record.source_id:
                raise ValueError("An index ID cannot change source ownership")
            category = (
                plan.added_ids
                if old is None
                else (
                    plan.embedding_invalidations
                    if old.embedding_key != record.embedding_key
                    else plan.metadata_update_ids
                )
            )
            if record.id not in category or old == record:
                raise ValueError("Plan upsert classification differs from acknowledged state")
        # Imported plans must satisfy the same collective source checks as
        # plan(). Validating each upsert alone cannot detect conflicting spans
        # between siblings, including siblings retained as unchanged records.
        resulting: dict[str, list[IndexRecord]] = {source_id: [] for source_id in sources}
        for record in (*plan.upserts, *(previous[key] for key in unchanged)):
            resulting[record.source_id].append(record)
        for source_id, records in resulting.items():
            _source_records(
                IndexSource(
                    source_id,
                    sources[source_id],
                    tuple(chunk_from_dict(record.metadata["omnichunk"]) for record in records),
                ),
                plan.model_revision,
                plan.preprocessing_revision,
                plan.use_contextualized_text,
            )
        if plan.complete_scope:
            members = {
                row[0]
                for row in self._conn.execute(
                    "SELECT source_id FROM scopes WHERE collection=? AND scope=?",
                    (plan.collection, plan.scope),
                )
            }
            other_owners = {
                row[0]
                for row in self._conn.execute(
                    "SELECT source_id FROM scopes WHERE collection=? AND scope<>?",
                    (plan.collection, plan.scope),
                )
            }
            required_deletions = members - set(sources) - other_owners
            if required_deletions - set(plan.deleted_sources):
                raise ValueError("Complete scope plan omits required stale source deletions")
        current = self._conn.execute(
            "SELECT * FROM collections WHERE name=?", (plan.collection,)
        ).fetchone()
        if current and (
            current["model"],
            current["preprocessing"],
            bool(current["contextualized"]),
        ) != (plan.model_revision, plan.preprocessing_revision, plan.use_contextualized_text):
            known = {
                row[0]
                for row in self._conn.execute(
                    "SELECT source_id FROM sources WHERE collection=?", (plan.collection,)
                )
            }
            if known - affected:
                raise IndexConflictError("Policy changes require every existing source")

    def enqueue(self, plan: IndexPlan) -> str:
        """Persist a validated plan and its outbox atomically; safe to retry."""
        body = plan.to_json()
        plan = IndexPlan.from_json(body)
        with self._transaction(write=True):
            existing = self._conn.execute(
                "SELECT body FROM plans WHERE id=?", (plan.plan_id,)
            ).fetchone()
            if existing:
                if existing[0] != body:
                    raise IndexConflictError("Plan ID already exists with different contents")
                return plan.plan_id
            current = self._conn.execute(
                "SELECT * FROM collections WHERE name=?", (plan.collection,)
            ).fetchone()
            if (current["generation"] if current else 0) != plan.base_generation:
                raise IndexConflictError("Stale plan generation; create a new plan")
            if current and current["target_id"] != plan.target_id:
                raise IndexConflictError("Collection is bound to a different target_id")
            if self._conn.execute(
                "SELECT 1 FROM plans WHERE collection=? AND done=0", (plan.collection,)
            ).fetchone():
                raise IndexConflictError("A collection plan is already pending")
            self._validate_transition(plan)
            if not current:
                self._conn.execute(
                    "INSERT INTO collections(name,target_id,model,preprocessing,contextualized) "
                    "VALUES(?,?,?,?,?)",
                    (
                        plan.collection,
                        plan.target_id,
                        plan.model_revision,
                        plan.preprocessing_revision,
                        int(plan.use_contextualized_text),
                    ),
                )
            self._conn.execute(
                "INSERT INTO plans(id,collection,body) VALUES(?,?,?)",
                (plan.plan_id, plan.collection, body),
            )
            operations: list[tuple[str, str, str | None]] = [
                ("delete", identifier, None) for identifier in plan.removed_ids
            ]
            operations.extend(
                ("upsert", record.id, canonical_json(asdict(record))) for record in plan.upserts
            )
            for sequence, (kind, identifier, record_body) in enumerate(operations):
                self._conn.execute(
                    "INSERT INTO operations(plan_id,sequence,operation_id,kind,record_id,body) "
                    "VALUES(?,?,?,?,?,?)",
                    (
                        plan.plan_id,
                        sequence,
                        digest([plan.plan_id, kind, identifier]),
                        kind,
                        identifier,
                        record_body,
                    ),
                )
            if not operations:
                self._finish(plan)
        return plan.plan_id

    def _finish(self, plan: IndexPlan) -> None:
        for identifier in plan.removed_ids:
            self._conn.execute(
                "DELETE FROM records WHERE collection=? AND id=?", (plan.collection, identifier)
            )
        for record in plan.upserts:
            self._conn.execute(
                "INSERT OR REPLACE INTO records(collection,id,source_id,body) VALUES(?,?,?,?)",
                (plan.collection, record.id, record.source_id, canonical_json(asdict(record))),
            )
        for source_id in plan.deleted_sources:
            self._conn.execute(
                "DELETE FROM sources WHERE collection=? AND source_id=?",
                (plan.collection, source_id),
            )
            self._conn.execute(
                "DELETE FROM scopes WHERE collection=? AND source_id=?",
                (plan.collection, source_id),
            )
        for source_id, revision in plan.source_revisions:
            self._conn.execute(
                "INSERT OR REPLACE INTO sources(collection,source_id,revision) VALUES(?,?,?)",
                (plan.collection, source_id, revision),
            )
        if plan.scope is not None:
            if plan.complete_scope:
                self._conn.execute(
                    "DELETE FROM scopes WHERE collection=? AND scope=?",
                    (plan.collection, plan.scope),
                )
            for source_id in plan.scope_source_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO scopes(collection,scope,source_id) VALUES(?,?,?)",
                    (plan.collection, plan.scope, source_id),
                )
        self._conn.execute(
            "UPDATE collections SET generation=?,model=?,preprocessing=?,contextualized=? "
            "WHERE name=?",
            (
                plan.base_generation + 1,
                plan.model_revision,
                plan.preprocessing_revision,
                int(plan.use_contextualized_text),
                plan.collection,
            ),
        )
        self._conn.execute("UPDATE plans SET done=1,error=NULL WHERE id=?", (plan.plan_id,))

    def deliver(
        self,
        sink: IndexSink,
        embed: Callable[[Sequence[str]], Sequence[Sequence[float]]] | None = None,
        *,
        collection: str = "default",
        batch_size: int = 64,
        max_batches: int | None = None,
        retry_failed: bool = False,
    ) -> DeliveryResult:
        """Deliver bounded batches; exact acknowledgements checkpoint durable work.

        A remote success followed by a crash is replayed. Prepared vectors were
        committed before remote I/O, so recovery reuses them. Unknown failures
        require explicit ``retry_failed=True``; retryable failures remain eligible.
        This method does not sleep or promise distributed exactly-once delivery.
        """
        name(collection, "collection")
        name(sink.target_id, "sink.target_id")
        if (
            type(batch_size) is not int
            or batch_size <= 0
            or (max_batches is not None and (type(max_batches) is not int or max_batches <= 0))
            or type(retry_failed) is not bool
        ):
            raise ValueError("Invalid delivery batch/retry limits")
        acknowledged = calls = reused = batches = 0
        active_id: str | None = None
        fresh: set[str] = set()
        while max_batches is None or batches < max_batches:
            failed: Exception | None = None
            with self._transaction(write=True):
                state = self._conn.execute(
                    "SELECT * FROM collections WHERE name=?", (collection,)
                ).fetchone()
                if state and state["target_id"] != sink.target_id:
                    raise IndexConflictError("Sink target_id differs from the collection binding")
                pending = self._conn.execute(
                    "SELECT * FROM plans WHERE collection=? AND done=0", (collection,)
                ).fetchone()
                if pending is None:
                    return DeliveryResult(active_id, acknowledged, 0, True, calls, reused)
                active_id = pending["id"]
                if pending["error"] and not pending["retryable"] and not retry_failed:
                    raise PermanentSinkError(
                        f"Pending delivery requires retry_failed=True: {pending['error']}"
                    )
                plan = IndexPlan.from_json(pending["body"])
                operations = self._conn.execute(
                    "SELECT * FROM operations WHERE plan_id=? AND acked=0 "
                    "ORDER BY sequence LIMIT ?",
                    (active_id, batch_size),
                ).fetchall()
                records = [_record(row["body"]) for row in operations if row["kind"] == "upsert"]
                cached: dict[str, tuple[float, ...]] = {}
                missing: dict[str, str] = {}
                self._conn.execute("SAVEPOINT delivery_batch")
                try:
                    for record in records:
                        row = self._conn.execute(
                            "SELECT vector FROM embeddings WHERE collection=? AND fingerprint=?",
                            (collection, record.embedding_key),
                        ).fetchone()
                        if row:
                            cached[record.embedding_key] = vector_values(
                                json.loads(row[0]), state["dimension"]
                            )
                        else:
                            missing[record.embedding_key] = record.text
                    if missing:
                        if embed is None:
                            raise ValueError(
                                "An embedding callback is required for uncached payloads"
                            )
                        calls += 1
                        values = list(embed(list(missing.values())))
                        if len(values) != len(missing):
                            raise ValueError(
                                "Embedding callback returned the wrong number of vectors"
                            )
                        vectors = []
                        dimension = state["dimension"]
                        for value in values:
                            vector = vector_values(value, dimension)
                            dimension = dimension or len(vector)
                            vectors.append(vector)
                        for fingerprint, vector in zip(missing, vectors):
                            self._conn.execute(
                                "INSERT OR REPLACE INTO embeddings(collection,fingerprint,vector) "
                                "VALUES(?,?,?)",
                                (collection, fingerprint, canonical_json(vector)),
                            )
                            fresh.add(fingerprint)
                        self._conn.execute(
                            "UPDATE collections SET dimension=? WHERE name=?",
                            (dimension, collection),
                        )
                        # Commit preparation before a separate transaction reselects
                        # pending work. Another worker may already deliver it.
                        continue
                    operation_ids = tuple(row["operation_id"] for row in operations)
                    batch = DeliveryBatch(
                        collection,
                        sink.target_id,
                        digest([active_id, operation_ids]),
                        tuple(
                            VectorRecord(
                                record.id,
                                record.source_id,
                                record.source_revision,
                                record.text,
                                record.metadata,
                                cached[record.embedding_key],
                            )
                            for record in records
                        ),
                        tuple(row["record_id"] for row in operations if row["kind"] == "delete"),
                        operation_ids,
                    )
                    receipt = sink.apply(batch)
                    if (
                        not isinstance(receipt, DeliveryReceipt)
                        or receipt.idempotency_key != batch.idempotency_key
                        or receipt.operation_ids != operation_ids
                    ):
                        raise AcknowledgementError(
                            "Sink receipt must match the submitted operation IDs and key"
                        )
                    self._conn.executemany(
                        "UPDATE operations SET acked=1 WHERE plan_id=? AND operation_id=?",
                        [(active_id, key) for key in operation_ids],
                    )
                    self._conn.execute(
                        "UPDATE plans SET error=NULL,retryable=1 WHERE id=?", (active_id,)
                    )
                    acknowledged += len(operations)
                    reused += sum(record.embedding_key not in fresh for record in records)
                    batches += 1
                    remaining = self._conn.execute(
                        "SELECT COUNT(*) FROM operations WHERE plan_id=? AND acked=0", (active_id,)
                    ).fetchone()[0]
                    if not remaining:
                        self._finish(plan)
                        return DeliveryResult(active_id, acknowledged, 0, True, calls, reused)
                except Exception as exc:
                    self._conn.execute("ROLLBACK TO delivery_batch")
                    self._conn.execute("RELEASE delivery_batch")
                    self._conn.execute(
                        "UPDATE plans SET error=?,retryable=? WHERE id=?",
                        (
                            f"{type(exc).__name__}: {exc}",
                            int(isinstance(exc, RetryableSinkError)),
                            active_id,
                        ),
                    )
                    failed = exc
            if failed is not None:
                raise failed
        status = self.status(collection=collection)
        return DeliveryResult(
            active_id,
            acknowledged,
            status.pending_operations,
            status.pending_plan_id is None,
            calls,
            reused,
        )

    def prune_embeddings(self, *, collection: str = "default") -> int:
        """Remove vectors unused by acknowledged records; reject pending plans."""
        name(collection, "collection")
        with self._transaction(write=True):
            if self._conn.execute(
                "SELECT 1 FROM plans WHERE collection=? AND done=0", (collection,)
            ).fetchone():
                raise IndexConflictError("Cannot prune embeddings while delivery is pending")
            keep = {record.embedding_key for record in self.records(collection=collection)}
            stale = [
                row[0]
                for row in self._conn.execute(
                    "SELECT fingerprint FROM embeddings WHERE collection=?", (collection,)
                )
                if row[0] not in keep
            ]
            self._conn.executemany(
                "DELETE FROM embeddings WHERE collection=? AND fingerprint=?",
                [(collection, key) for key in stale],
            )
            return len(stale)
