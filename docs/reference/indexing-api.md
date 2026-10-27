# Indexing and integration API

For a complete, runnable workflow and its delivery guarantees, see the
[indexing guide](../indexing.md). Imports below are from `omnichunk` unless a
module is specified. Method signatures and defaults are generated from source.

## Local chunk store

`ChunkStore(path, collection="default")` opens a SQLite file at `path`; use a
context manager or call `close()`. `collection` names the logical chunk collection.
`query(filepath)` returns stored chunks for that path. `index(root, ...)` reprocesses
matching files; `sync(root, ...)` skips unchanged files and configurations. Both
return `SyncResult`. `root` is the directory to scan; `glob` (default `"**/*"`)
selects files, `exclude` is a sequence of exclusion patterns, `include_hidden`
defaults to `False`, and `encoding` defaults to `"utf-8"`. Supply either a configured `chunker` or chunker keyword options for processing;
passing both raises `ValueError`. A successful scan may remove missing
files within its previously owned scope; consult the guide before changing filters.

`SyncResult` exposes `files_scanned`, `files_skipped`, `files_updated` and
`files_deleted` counts, `removed_chunk_ids` for downstream deletions, and
`diffs` keyed by filepath. Delete the removed IDs before upserting each diff's
added chunks; refresh locations for unchanged chunks when needed. Migration
requires separate `source` and nonexistent `destination` paths, with an optional
collection name. Its `MigrationResult` reports file/chunk counts, `id_map` and
whether reindexing is required.

::: omnichunk.store.ChunkStore

::: omnichunk.store.SyncResult

::: omnichunk.store.migrate_legacy_store

::: omnichunk.store.MigrationResult

::: omnichunk.store.LegacyStoreError

## Journal and delivery

`IndexJournal(path)` uses its own SQLite file, separate from `ChunkStore`.
`plan(sources, *, target_id, model_revision, ...)` produces an `IndexPlan`
without writing to a vector backend. Each `IndexSource` has a stable `source_id`,
source `revision`, a tuple of `chunks`, and optional JSON-compatible `metadata`.
`collection` defaults to `"default"`; `target_id` identifies the backend target;
`model_revision` is required and `preprocessing_revision` defaults to
`"identity-v1"`; together they identify embedding behavior.
`use_contextualized_text=True` selects the contextualized embedding payload;
set it to `False` for raw chunk text. Set `scope` and
`complete_scope=True` only for a complete scan; `delete_sources` explicitly removes
the specified source IDs. Enqueue the plan before delivery.

`deliver(sink, embed, *, collection="default", batch_size=64, max_batches=None,
retry_failed=False)` sends bounded batches. `embed` accepts a sequence of texts
and returns corresponding vectors; it can be omitted when no uncached embeddings
are needed. `max_batches` limits work per call; `retry_failed` permits retry of
previously permanent or unclassified failures. The sink's `target_id` must match
the plan. `DeliveryResult` reports completed and pending work; `status()` reports
the journal's current state. Delivery is at least once, so sinks must be idempotent.

For `IndexPlan`, `base_generation` is the collection generation used to create
the plan; `upserts` contains `IndexRecord` values to write, while `removed_ids`
lists IDs to delete. `added_ids`, `metadata_update_ids`, `embedding_invalidations`
and `unchanged_ids` classify the comparison with the previous state. `plan_id`
identifies the plan and `schema_version` versions its JSON representation.
`DeliveryBatch` contains the collection, target, idempotency key, vector
`upserts`, `deletes` and operation IDs. A custom `IndexSink.apply(batch)` must
return a `DeliveryReceipt` with the matching key and exactly those operation IDs.
`DeliveryResult` counts acknowledged and pending operations, model calls and reused
embeddings; `completed` indicates whether delivery finished. `IndexStatus`
contains the current generation, pending plan and operation counts, last error,
and whether that error is retryable.

::: omnichunk.indexing.IndexJournal

::: omnichunk.indexing.IndexSource

::: omnichunk.indexing.IndexPlan

::: omnichunk.indexing.IndexRecord

::: omnichunk.indexing.VectorRecord

::: omnichunk.indexing.DeliveryBatch

::: omnichunk.indexing.DeliveryReceipt

::: omnichunk.indexing.DeliveryResult

::: omnichunk.indexing.IndexStatus

::: omnichunk.indexing.IndexSink

::: omnichunk.indexing.IndexConflictError

::: omnichunk.indexing.JournalSchemaError

::: omnichunk.indexing.RetryableSinkError

::: omnichunk.indexing.PermanentSinkError

::: omnichunk.indexing.AcknowledgementError

## Backend and framework adapters

`QdrantSink(client, *, target_id, collection_name, dimensions)` uses a
caller-configured Qdrant client and an existing physical collection. `PgvectorSink`
accepts a caller-owned `connection`, `target_id`, `dimensions` and optional SQL
`table` (default `"omnichunk_vectors"`); call `initialize()` explicitly with
an idle connection and sufficient database privileges. Both require a positive
vector dimension. Qdrant retrieval should filter by logical `collection` and
application-owned access metadata.
The [guide](../indexing.md#7-connect-a-vector-backend) includes setup recipes.

::: omnichunk.indexing.sinks.QdrantSink

::: omnichunk.indexing.sinks.PgvectorSink

::: omnichunk.indexing.sinks.qdrant_point_id

Framework adapters require their respective optional dependencies.
`OmniChunkTextSplitter` and `OmniChunkNodeParser` accept an `options` mapping
with the same [chunk options](options.md), `filepath="document.txt"`, optional
`levels` for hierarchical output, and `use_contextualized_text=False` to select
raw text by default. The LlamaIndex parser requires JSON-serializable options and
does not support `id_func`. `OmniChunkIngestionPipeline` accepts LlamaIndex
pipeline arguments and requires `OmniChunkNodeParser` as its first transformation;
it creates one by default.
See the [framework guide](../indexing.md#6-use-native-framework-pipelines) for
document identities, caching and complete examples.

::: omnichunk.integrations.langchain.OmniChunkTextSplitter

::: omnichunk.integrations.llamaindex.OmniChunkNodeParser

::: omnichunk.integrations.llamaindex.OmniChunkIngestionPipeline
