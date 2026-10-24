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

Vector export helpers produce data dictionaries, not network requests. Adapt them
to the installed client version: Pinecone namespaces belong on the upsert request
(leave the helper's `namespace` empty for individual vectors); Weaviate Python v4
uses `uuid=row["id"]`, `properties=row["properties"]`, and
`vector=row["vector"]`. Use `weaviate_object_id(chunk_id)` to translate removed
chunk IDs into the same deterministic UUIDs used during export. See
[example 11](https://github.com/oguzhankir/omnichunk/blob/main/examples/11_vector_db_export.py).

The example applies diffs to an in-memory dictionary in one process. SQLite sync
and a remote vector write are **not one transaction**: if the process fails after
sync, the next scan can skip those files without replaying their previous diffs.
A production integration needs durable delivery/reconciliation or a new retrieval
generation built from stored chunks and switched after validation. Keep the
previous generation for rollback. Durable connector delivery is tracked in the
[roadmap](https://github.com/oguzhankir/omnichunk/blob/main/ROADMAP.md).

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
