# Index, retrieve and synchronize

The [local RAG lifecycle example](https://github.com/oguzhankir/omnichunk/blob/main/examples/13_local_rag_lifecycle.py)
demonstrates the complete path from source files to cited retrieval context. It
runs without a service, API key or model download:

```bash
pip install -e .
python examples/13_local_rag_lifecycle.py
```

It creates a temporary policy corpus, indexes it into SQLite, retrieves the backup
retention policy, then edits that policy and deletes an obsolete document. Its
assertions check exact citation bytes, removal of stale chunks, repeat-sync skips
and persistence after reopening SQLite. Retrieval is a small lexical baseline;
it demonstrates the lifecycle, not semantic search quality or answer generation.

## 1. Choose the chunk contract

```python
from omnichunk import Chunker
from omnichunk.store import ChunkStore

chunker = Chunker(
    max_chunk_size=512,
    size_unit="chars",
    context_mode="none",
    coverage_policy="lossless",
)
with ChunkStore("index.sqlite", collection="policies") as store:
    result = store.sync("policies", glob="**/*.txt", chunker=chunker)
```

`sync()` indexes a new source, reprocesses changed content or configuration, and
skips unchanged sources. Each SQLite sync commits atomically. A failed scan
raises and preserves the previous store state. Deletion applies only to missing
files owned by a previous completed scan with the same root and filters.

Use a stable logical `source_id` for a single document whose filename can change.
Do not configure one shared `source_id` for every file in a directory. For model
token limits, configure an explicit matching tokenizer as described in
[installation](install.md) and [contracts](reference/contracts.md).

## 2. Apply the changes to your retriever

`ChunkStore` persists chunks; it is not a vector search engine. For each committed
`SyncResult`:

1. Delete `removed_chunk_ids` from the retrieval index.
2. Embed and upsert each diff's `added` chunks using `contextualized_text`.
3. Refresh metadata for `unchanged` chunks without recomputing their vectors.

The `updated` list is a subset of `added`. A changed embedding payload can retain
the same stable ID and appear in both removals and additions, so deletion must
precede upsert. Unchanged payloads can move to new source offsets; refreshing
citation metadata prevents stale references.

Include the embedding model and preprocessing revision alongside
`chunk_embedding_fingerprint()` in your embedding cache key. Stable chunk IDs
identify occurrences; they do not prove an existing embedding is reusable.
Persist complete records with `chunk_to_dict()` and recover with
`chunk_from_dict()` when metadata must survive a round trip.

Vector export helpers produce data dictionaries, not network requests. Use
`chunks_to_pinecone_upsert_request()` for Pinecone: its `namespace` belongs to the
request envelope, and its validated records preserve complete metadata as JSON.
The legacy row helper retains its old shape for compatibility. Weaviate Python v4
uses `uuid=row["id"]`, `properties=row["properties"]`, and
`vector=row["vector"]`. Use `weaviate_object_id(chunk_id)` to translate removed
chunk IDs into the same deterministic UUIDs used during export. See
[example 11](https://github.com/oguzhankir/omnichunk/blob/main/examples/11_vector_db_export.py).

The example applies diffs to an in-memory dictionary in one process. SQLite sync
and a remote vector write are **not one transaction**: if the process fails after
sync, the next scan can skip those files without replaying their previous diffs.
Use the acknowledged journal workflow below when writes must survive interruption.
`ChunkStore` continues to provide its existing local chunk cache; its schema and
`SyncResult` delivery semantics are unchanged.

## 3. Retrieve, budget and cite

Rank chunks with your chosen lexical, vector or hybrid retriever. Construct the
LLM prompt from `contextualized_text`; cite `text` using its source descriptor and
byte/line ranges. Size the complete prompt, including labels, separators, system
instructions and reserved answer tokens. A per-chunk limit does not establish a
whole-prompt limit.

For UTF-8 text, the source-slice check is:

```python
raw = source_text.encode("utf-8")
assert raw[chunk.byte_range.start:chunk.byte_range.end].decode("utf-8") == chunk.text
```

Keep a source revision or canonical-text snapshot with the citation. Reading a
later file revision may resolve the old offsets to different text. For PDF, DOCX
and notebooks, byte ranges refer to canonical extracted text, not binary files or
notebook JSON; keep loader page/cell metadata for links back to the container.

## 4. Evaluate an index generation

Use representative questions with relevant source spans. Compare retrieval
recall/ranking, citation correctness, payload overflow, index size, embedding
cost, elapsed time and memory under the same model and retrieval settings.
Validate edits, deletions and failed deliveries as well as the first ingestion.
Structural chunk tests and throughput measurements alone do not demonstrate
better answers. See [performance methodology](performance/sla.md) and the
[migration guide](migrations/v2.md) before replacing an existing collection.

## 5. Persist delivery work before touching the retrieval backend

The [recoverable indexing example](https://github.com/oguzhankir/omnichunk/blob/main/examples/14_recoverable_indexing.py)
uses two SQLite files to demonstrate a journal and an independent retrieval
backend. It deliberately loses a receipt after a remote commit, closes the
journal, then resumes delivery without recomputing the embedding. It also shows
metadata-only ACL updates, authorized retrieval and source deletion:

```bash
python examples/14_recoverable_indexing.py
```

`IndexJournal` stores serializable plans, prepared vectors and acknowledgment
checkpoints in a separate database. A plan is a dry run until `enqueue()` commits
it. Chunking and source enumeration must finish before publishing a complete
scope. Applications supply canonical source revisions and explicit model and
preprocessing revisions:

```python
from omnichunk import Chunker
from omnichunk.indexing import IndexJournal, IndexPlan, IndexSource

chunks = Chunker(context_mode="none").chunk(
    "retention.txt", "Backups expire after thirty days.", source_id="retention-policy"
)
source = IndexSource(
    "retention-policy",
    chunks[0].source.revision,
    tuple(chunks),
    metadata={"acl": ["support"], "classification": "internal"},
)
with IndexJournal("delivery.sqlite") as journal:
    plan = journal.plan(
        [source],
        collection="policies",
        target_id="production-policies-v1",
        model_revision="my-embedding-model@revision-1",
        preprocessing_revision="canonical-payload-v1",
        scope="policy-documents",
        complete_scope=True,
    )
    print(plan.added_ids, plan.removed_ids, plan.metadata_update_ids)
    validated_plan = IndexPlan.from_json(plan.to_json())
    journal.enqueue(validated_plan)
    # A configured sink must expose the same target_id.
    # journal.deliver(sink, embed, collection="policies", batch_size=64, max_batches=10)
```

The plan records exact embedding payload hashes alongside model/preprocessing
revisions. Unchanged payloads reuse persisted vectors, including metadata-only
updates and retries after a lost receipt. A revision string identifies behavior;
the application must change it when its model or preprocessing changes. Validate
the intended embedding dimension and start a new target when changing dimensions.

`plan.to_json()`/`IndexPlan.from_json()` validate the schema, identities and content
digest. Generation checks reject stale plans; only one plan can be pending per
collection. A target identity is bound persistently to that collection. Use a
distinct identity for a different endpoint, index or namespace and a separate
journal/collection when migrating. The application remains responsible for
binding that identity to the correct authenticated backend client.

### Delivery, retries and visibility

A sink implements `apply(DeliveryBatch) -> DeliveryReceipt`. It receives bounded
upserts/deletions, a stable idempotency key and operation IDs. Return a receipt only
after the backend confirms completion, and echo exactly those IDs. Partial,
missing or mismatched acknowledgment leaves work pending. Qdrant and pgvector
adapters are available from `omnichunk.indexing.sinks`; install their optional
extras and configure the backend explicitly.

Prepared vectors commit before the remote write. A successful backend write
followed by a process crash can be delivered again: sinks must support idempotent
upserts and deletions. This is at-least-once delivery. `records()` exposes the
last fully acknowledged state, while `status()` identifies pending work and errors.
The remote backend can already contain some writes before that plan completes;
use separate retrieval generations and an application-controlled switch if readers
require an atomic view of a complete corpus update.

`RetryableSinkError` permits another `deliver()` attempt; permanent or unclassified
failures require investigation followed by `retry_failed=True`. Calls do not sleep
or silently retry indefinitely. Bound `batch_size` and `max_batches`, configure
backend request timeouts, and let the application schedule retries with backoff.

One SQLite writer serializes delivery within a journal and holds a write lock
during each remote batch and its acknowledgment. This prevents another worker
from replaying an older batch after a newer plan, but a slow backend blocks other
writes to that journal. Use independent journal files for independent workloads;
do not point multiple journals at the same owned collection.

### Scoped cleanup and authorization

Use `scope` plus `complete_scope=True` only for a complete successful snapshot.
Missing sources previously owned only by that scope become explicit deletion work;
another scope's ownership preserves a shared source. A partial scan does not assert
deletion. `delete_sources=(source_id,)` removes
an explicitly identified source in the selected collection. Always consume
fallible enumerators before accepting their output as a complete scope. Collections
and scope membership are data ownership boundaries, not user authorization.

Caller metadata such as ACLs is carried to the backend. The application must
enforce it during retrieval. The offline example filters the stored ACL before
ranking and never returns excluded candidate counts. In a service, obtain the
principal and allowed collection from authenticated identity, recheck permissions
before returning results, and invalidate caches after ACL changes. Storing an ACL
without applying a retrieval filter grants no protection.

### Migration and rollback

Create a new journal database and a new backend target; do not open an existing
`ChunkStore` database as an `IndexJournal`. Reconstruct complete `IndexSource`
snapshots from canonical source documents or cached chunks, enqueue their initial
plans, and finish delivery. Compare record counts, citations and representative
retrieval results before switching the application to the new target. Keep the
old target and its configuration available until the new deployment is accepted;
rollback switches retrieval back to that target. After acceptance, delete the old
target through its own lifecycle rather than replaying old deletions into the new
collection. Back up the journal together with its target identity and model
configuration; losing the journal requires rebuilding/reconciling a fresh target.

## 6. Use native framework pipelines

Install the corresponding `langchain` or `llamaindex` extra. Give each source a
stable document ID across edits; without an ID or source/path metadata, the
LangChain adapter falls back to a content hash that changes on edit.

```python
from langchain_core.documents import Document
from omnichunk.integrations.langchain import OmniChunkTextSplitter

splitter = OmniChunkTextSplitter(
    options={"max_chunk_size": 256, "context_mode": "none"}
)
documents = splitter.split_documents([
    Document(id="policy-1", page_content="Keep backups for thirty days.",
             metadata={"acl": ["support"], "filepath": "policy.txt"})
])
assert documents[0].metadata["acl"] == ["support"]
```

The native LlamaIndex parser also works as an ingestion transformation:

```python
from llama_index.core import Document
from omnichunk.integrations.llamaindex import OmniChunkNodeParser

parser = OmniChunkNodeParser(
    options={"max_chunk_size": 256, "context_mode": "none"}
)
nodes = parser.get_nodes_from_documents([
    Document(id_="policy-1", text="Keep backups for thirty days.",
             metadata={"acl": ["support"], "filepath": "policy.txt"})
])
assert nodes[0].ref_doc_id == "policy-1"
```

Both preserve caller metadata under its original keys and complete chunk records
under `metadata["omnichunk"]["chunk"]`. The reserved key rejects already-chunked
input, preventing accidental double splitting. Raw text is the default output;
`use_contextualized_text=True` selects the rendered chunk payload. LlamaIndex
excludes metadata from model rendering so it cannot repeat that payload.

Pass `levels=[128, 512]` for all-level hierarchy. IDs are qualified by level;
LlamaIndex nodes expose source, parent/child and same-level sibling relationships.
Select the intended level for embedding/retrieval rather than indiscriminately
indexing all levels. The LlamaIndex transform serializes its configuration for
ingestion caching and rejects opaque callable options; use named tokenizers.
See the [tested version matrix](install.md#native-integration-compatibility).

## 7. Connect a vector backend

- [Qdrant recipe](https://github.com/oguzhankir/omnichunk/blob/main/examples/integrations/qdrant_indexing.py)
  uses a real local client, namespaced UUIDs, acknowledged writes, ACL filtering,
  exact citations and deletion. Install `omnichunk[qdrant]`.
- [pgvector recipe](https://github.com/oguzhankir/omnichunk/blob/main/examples/integrations/pgvector_indexing.py)
  uses a caller-configured PostgreSQL connection and a vector table with
  `(collection, id)` ownership. Install `omnichunk[pgvector]` and provision a server
  with the vector extension. Each batch commits before acknowledgment; an existing
  outer transaction is rejected.

Both preserve nested metadata and validate complete batches before deletion.
Qdrant waits for completed operations; its logical record IDs map through
`qdrant_point_id(collection, record_id)` for both upserts and deletes. Configure
network timeouts on the underlying client/connection. Plans and source snapshots
remain resident during processing; batch limits bound embedding requests and
remote writes, not total corpus memory.

For Pinecone, `chunks_to_pinecone_upsert_request()` builds
`index.upsert(**request)` with `namespace` on the request envelope. Complete chunk
metadata is JSON-encoded in the flat `omnichunk` metadata field; pass explicit
scalar/string-list `filter_metadata` for queryable ACL/source/page attributes.
Unsupported values, collisions and metadata over 40 KiB are rejected. The legacy
row helper remains available, but its per-row namespace is not an SDK request.
