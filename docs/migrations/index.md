# Upgrade notes

For the current foundation transition, start with the
[1.x → 2.x migration guide](v2.md). The notes below describe historical releases,
not current identity or server guarantees.

This page consolidates historical upgrade notes for v0.8–v0.10. These releases
added optional workflows; existing basic chunking calls generally remained
compatible. For exhaustive release history, see the
[changelog](https://github.com/oguzhankir/omnichunk/blob/main/CHANGELOG.md).

| Version | Notes |
|--------|--------|
| [v0.8](#v08) | Hierarchical chunking, `chunk_diff`, token budget optimizer |
| [v0.9](#v09) | Multiformat loaders, dedup, `omnichunk eval` |
| [v0.10](#v010) | Chunk store, streaming upsert, MCP serve, OpenTelemetry |

## v0.8

v0.8 adds optional workflows; existing `chunk()` / `chunk_file()` usage remains valid.
No breaking changes are required for basic chunking callers; the new APIs are additive.

### Hierarchical chunking

Use when you need multiple granularities (leaves for embeddings, roots for LLM context):

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=256, size_unit="chars")
tree = chunker.hierarchical_chunk("api.py", source, levels=[64, 256, 1024])
```

### Incremental diff

Use when syncing a vector database with file updates:

```python
from omnichunk import Chunker

chunker = Chunker()
new_chunks = chunker.chunk("api.py", new_source)
diff = chunker.chunk_diff("api.py", new_source, previous_chunks=old_chunks)
# diff.added, diff.removed_ids, diff.unchanged
```

Stable IDs align with `stable_chunk_id()` and vector export row IDs from earlier releases.

### Token budget selection

```python
from omnichunk.budget import TokenBudgetOptimizer

opt = TokenBudgetOptimizer(budget=4096, strategy="greedy")
result = opt.select(retrieved_chunks, scores=scores)
```

## v0.9

### Multiformat and binary formats

`chunk_file()` / `Chunker.chunk_file()` now take an explicit `encoding` argument
(default `utf-8`). If you relied on implicit defaults only, behavior is unchanged
for UTF-8 text files.

Structured formats (`.ipynb`, `.tex`, `.pdf`, `.docx`) are routed through dedicated
loaders when using `chunk_file()` / `chunk_directory()`. Pass PDF and DOCX paths to
`chunk_file()`; reading these binary formats as plain text will not work.

`.ipynb` and `.tex` can be passed as string content to `Chunker.chunk()`.
`.pdf` and `.docx` require `chunk_file()` because they are binary formats.

### New APIs (additive)

- `dedup_chunks()` for near-duplicate removal
- `evaluate_chunks()` and CLI `omnichunk eval` for offline quality metrics
- `chunk_from_dict()` for JSONL round-trips

Review the changelog for any edge-specific behavior changes in loaders; typical
chunking pipelines remain compatible.

## v0.10

### Chunker options merging

`Chunker` option merging uses `dataclasses.replace()` instead of `asdict()` so
callable fields (e.g. `otel_tracer`, `semantic_embed_fn`) are not deep-copied.

If you passed custom callables through `ChunkOptions`, they should now round-trip
reliably. If you relied on accidental deep-copy side effects, treat this as a bugfix.

### New infrastructure APIs (additive)

- `ChunkStore` for SQLite-backed incremental indexing
- `Chunker.stream_upsert()` for batched vector-export rows
- `omnichunk serve --mcp` for JSON-RPC tools
- `ChunkOptions.otel_tracer` for optional tracing

No breaking changes are expected for core chunking callers; these features are opt-in.
