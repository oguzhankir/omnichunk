# Chunking in practice

This guide shows common workflows with the base installation. See the
[Python API reference](reference/chunker.md) for signatures and the
[source and budget contracts](reference/contracts.md) for guarantees and tradeoffs.

## Chunk text and inspect its source

```python
from omnichunk import Chunker

text = "# Backups\n\nRetain backups for 30 days.\n\nTest restoration weekly.\n"
chunker = Chunker(max_chunk_size=80, context_mode="none")
chunks = chunker.chunk("policy.md", text, source_id="policy:backup")

for part in chunks:
    print(part.index, part.text, part.context.heading_hierarchy)
    original = text.encode("utf-8")[part.byte_range.start:part.byte_range.end]
    assert original.decode("utf-8") == part.text
    assert part.source.source_id == "policy:backup"
```

`filepath` labels the source and helps select a parser; it need not name an
existing file when passing `content` directly. Use a stable `source_id` when the
same logical document can be renamed. `text` is the exact source slice;
`contextualized_text` may include derived context and is suitable as an
embedding payload. Byte offsets are zero-based, half-open **UTF-8 bytes**, not
Python character indexes. Line ranges are zero-based and inclusive. Inspect
`context.parse_errors` for reported parser/loader problems.

Constructor options are reusable defaults; supported keyword overrides apply to
one call. The options below select the unit and size limit for the *rendered*
payload. Context takes space within that limit, so raw text may be smaller.

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=80, context_mode="none")
small = chunker.chunk("notes.txt", "A sentence. " * 20, max_chunk_size=40)
assert all(len(part.contextualized_text) <= 40 for part in small)
# The default for the next call remains 80.
assert chunker.config_fingerprint()
```

`size_unit="chars"` counts Unicode characters; `"nws"` counts non-whitespace
characters. For a model limit use `size_unit="tokens"` and a matching tokenizer.
A counting callable is accepted, but its count must match the downstream model
and include any special tokens the model adds. `"approximate"` explicitly opts
into estimates. See [installation](install.md) for named tokenizer extras.

## Keep every source byte

The default `coverage_policy="retrieval"` may omit whitespace-only spans. Use
`lossless` and inspect the manifest when every byte matters:

```python
from omnichunk import Chunker

source = "First paragraph.\n\nİkinci paragraf.\n"
result = Chunker(max_chunk_size=20, context_mode="none", coverage_policy="lossless") \
    .chunk_with_manifest("notes.txt", source)
assert not result.skipped_ranges
assert b"".join(c.text.encode("utf-8") for c in result.chunks) == source.encode("utf-8")
print(result.source.revision, result.diagnostics)
```

`skipped_ranges` reports uncovered byte intervals. The concatenation check above
assumes no numeric overlap: with overlap, use the union of ranges instead.
Container formats need to be loaded first; their coordinates refer to canonical
extracted text, not the original PDF, DOCX, or notebook container bytes.

## Read files and directories

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from omnichunk import Chunker

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "one.txt").write_text("Keep records for one year.", encoding="utf-8")
    chunker = Chunker(max_chunk_size=128, context_mode="none")
    one_file = chunker.chunk_file(str(root / "one.txt"), encoding="utf-8")
    results = chunker.chunk_directory(str(root), glob="**/*.txt", concurrency=2)
    for result in results:
        if result.error is not None:
            raise RuntimeError(f"{result.filepath}: {result.error}")
        print(result.filepath, len(result.chunks))
    assert one_file
```

`chunk_file()` reads a file. `chunk_directory()` returns a `BatchResult` per
matched file: check `error` before consuming `chunks`. `glob`, `exclude`,
`include_hidden`, `encoding`, and `concurrency` control discovery and processing.
Format extras are required for PDF and DOCX; consult [installation](install.md).
Directory and batch calls collect their results, so budget memory accordingly.

## Stream or process a batch

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=40, context_mode="none")
for part in chunker.stream("notes.txt", "A sentence. " * 20):
    assert part.total_chunks == -1  # count is unknown during iteration

results = chunker.batch([
    {"filepath": "a.txt", "code": "First document."},
    {"filepath": "b.txt", "code": "Second document.", "max_chunk_size": 30},
], concurrency=2)
for result in results:  # input order, even if workers finish out of order
    if result.error:
        raise RuntimeError(result.error)
    print(result.filepath, len(result.chunks))
```

`stream_file()` reads from disk and yields chunks. Streaming yields output
incrementally but source and parser state remain resident. Async applications can use `achunk`, `astream`, or `abatch`. The async
methods use worker threads; `astream`'s `buffer_size` bounds its output queue,
not total document memory. Cancellation waits for an active parser/provider call
to return.

## Build a hierarchy

```python
from omnichunk import Chunker

source = "One sentence. Two sentences. Three sentences. " * 8
chunker = Chunker(context_mode="none")
tree = chunker.hierarchical_chunk("notes.txt", source, levels=[40, 120])
print(len(tree.leaves()), len(tree.roots()))
for leaf in tree.leaves():
    parent = tree.parent(leaf)
    if parent is not None:
        print(leaf.text, parent.text)
```

Levels are chunk-size limits in the selected `size_unit`, ordered from fine to
coarse. Choose a level for retrieval; embedding every level increases index size
and can retrieve overlapping content. Hierarchy accepts canonical text; load
structured documents before passing their extracted text with a text filepath.

## Choose a boundary policy

Start with the default structural and sentence boundaries. For a smaller index,
evaluate the optional policies on representative retrieval questions:

```python
from omnichunk import Chunker

compact_prose = Chunker(max_chunk_size=120, context_mode="none",
                        prose_boundary_policy="compact")
compact_code = Chunker(max_chunk_size=120, context_mode="none",
                       code_boundary_policy="compact")
packed_markdown = Chunker(max_chunk_size=120, context_mode="none",
                          markdown_paragraph_policy="pack")

chunks = compact_prose.chunk("notes.txt", "A useful explanation. " * 30)
assert all(len(part.contextualized_text) <= 120 for part in chunks)
```

Compact prose can split otherwise fitting sentences while filling oversized
paragraphs. Compact code compares source layouts and can divide expressions in
oversized declarations; it retains fitting protected definitions when a valid
layout is available, otherwise raising an actionable error. Markdown packing
combines adjacent prose paragraphs within a heading while keeping table, list and
fence boundaries. These are independent settings, not automatic quality tuning.
They can reduce index work and also lower retrieval quality. Compare recall,
precision and embedding/index size before switching. The
[options reference](reference/options.md) lists defaults and constraints.

## Compare document revisions

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=80, context_mode="none")
old = chunker.chunk("policy.txt", "Retain backups for 30 days.")
diff = chunker.chunk_diff("policy.txt", "Retain backups for 60 days.", previous_chunks=old)
print("remove", diff.removed_ids)
print("upsert", [c.text for c in diff.added])
print("metadata refresh", len(diff.unchanged))
```

For a vector index, delete `removed_ids` before upserting `added`. `updated` is a
subset of `added` and can share an ID with a removed record. Refresh metadata for
`unchanged` chunks as source locations may move. Stable IDs identify occurrences;
cache embeddings using the embedding payload and model revision as well. For a
complete persistent workflow, see [indexing](indexing.md).
