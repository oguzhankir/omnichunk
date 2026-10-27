# Chunking API

Use a reusable `Chunker` when processing several documents with the same
configuration. The module-level functions create a fresh instance for each
call. Both interfaces return the same chunk models and apply the same source,
overlap and rendered-payload policies. See [chunk options](options.md) for every
configuration field and [contracts](contracts.md) for coverage and budget
guarantees. The generated signatures below come from `mkdocstrings`.

## Construct a chunker

`Chunker(*, registry=None, **options)` accepts keyword arguments only. `options`
are the public fields of `ChunkOptions`; they become defaults for later calls.
Methods with `**overrides` accept those same fields for one call without changing
the instance defaults. Unknown or internal option names raise `TypeError`;
invalid types, values or combinations raise `TypeError` or `ValueError` during
validation.

The defaults include `max_chunk_size=1500`, `min_chunk_size=50`,
`size_unit="chars"` and `context_mode="full"`. The maximum measures the final
`contextualized_text`, including rendered context. The minimum is a packing
preference, so structural boundaries and short tails can produce smaller chunks.
Supplying a maximum without a minimum reduces the default minimum when needed;
an explicit minimum greater than the maximum is invalid. For token limits, pass
both `size_unit="tokens"` and a tokenizer matching the downstream model.

`registry` must be a `PluginRegistry` or `None`. Passing a registry uses that
instance's parsers and formatters. With `None`, construction takes a snapshot of
the legacy global registrations. Later global registrations do not change that
snapshot. The registry and semantic embedding cache are reused across calls on
the same chunker.

```python
from omnichunk import Chunker, PluginRegistry

chunker = Chunker(
    registry=PluginRegistry(),
    max_chunk_size=256,
    size_unit="chars",
    context_mode="none",
)
text = "A document can contain several useful facts. " * 20
chunks = chunker.chunk("notes.txt", text)
smaller = chunker.chunk("notes.txt", text, max_chunk_size=80)
assert all(len(c.contextualized_text) <= 80 for c in smaller)
# The next call still uses the instance's 256-character maximum.
```

## Chunk text and inspect coverage

`chunk(filepath, content, **overrides) -> list[Chunk]` takes a source label and
already available text. For ordinary text formats, `filepath` does not need to
exist: its extension helps select a language and engine, and it supplies the
default source identity. `language`, `content_type` and `source_id` can override
those choices. This method does not read a file.

The list is in source order. Each chunk has a zero-based `index` and a known
`total_chunks`. `text` is the source slice; `contextualized_text` is the payload
with any rendered context. `byte_range` is a half-open UTF-8 range into canonical
text, and `line_range` uses zero-based inclusive line endpoints. Structured
context, source identity and budget information remain available on the chunk.
The default retrieval coverage policy can omit whitespace-only output, so empty
or whitespace-only input can return `[]`.

`stream(filepath, content, **overrides) -> Iterator[Chunk]` uses the same
finalization and options, but yields each chunk with `total_chunks=-1`. Errors
can arise while iterating. It avoids collecting the ordinary output list;
complete source text, indexes and parser state still remain resident, and
structured or semantic processing may buffer document candidates.

Text calls recognize `.ipynb`, `.tex` and `.rst` labels and load their contents
into canonical text. PDF and DOCX are binary formats: `chunk()` and `stream()`
reject those suffixes and require `chunk_file()` instead.

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=100, context_mode="none")
text = "First fact. Second fact. " * 20
for part in chunker.stream("facts.txt", text):
    assert part.total_chunks == -1
    assert text.encode("utf-8")[part.byte_range.start:part.byte_range.end].decode() == part.text
    print(part.index, part.text)
```

`chunk_with_manifest(filepath, content, **overrides) -> ChunkResult` also returns
the source descriptor when there are no chunks. Its `chunks` field is a tuple,
`skipped_ranges` records omitted source-byte spans, and `diagnostics` contains
deduplicated parse errors. It accepts canonical text only and rejects structured
document suffixes, including `.ipynb`, `.tex` and `.rst`. Load those formats
explicitly and use a plain-text label for the extracted text.

```python
from omnichunk import Chunker

result = Chunker(context_mode="none").chunk_with_manifest("blank.txt", " \n\t")
assert result.chunks == ()
assert result.skipped_ranges[0].start == 0
assert result.skipped_ranges[0].end == len(" \n\t".encode("utf-8"))
print(result.source.revision)
```

## Read files and directories

`chunk_file(path, *, encoding="utf-8", **overrides) -> list[Chunk]` reads one
local file. Text decoding preserves line endings. Notebook, LaTeX,
reStructuredText, PDF and DOCX suffixes use their corresponding loaders; binary
loaders require their optional dependencies. Coordinates describe the extracted
canonical UTF-8 text, rather than bytes in a PDF/DOCX container or a differently
encoded input file. Read, decode and chunking errors propagate to the caller.

`stream_file(path, *, encoding="utf-8", **overrides) -> Iterator[Chunk]` reads
one file and yields chunks with `total_chunks=-1`. Ordinary files still load
their whole text. PDF and DOCX currently collect their chunk list before yielding.
`encoding` applies to text input, while PDF and DOCX loaders read binary bytes.

`chunk_directory(path, *, glob="**/*", exclude=None, concurrency=10,
encoding="utf-8", include_hidden=False, **overrides) -> list[BatchResult]`
collects matching files and processes them in a thread pool. `glob` is relative
to the directory; `exclude` uses `fnmatch` patterns against relative POSIX paths.
Hidden path components are skipped unless `include_hidden=True`. Results are
sorted by file path, independently of completion order. Concurrency is clamped
to at least one worker and at most the number of files. A file path produces a
single result; a missing root raises `FileNotFoundError`; no matches returns
`[]`.

Each `BatchResult` has `filepath`, `chunks` and `error`. Check `error` before
indexing its chunks: per-file read/chunk failures are reported there instead of
stopping other files. Invalid configuration can still raise an exception.

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=512, context_mode="none")
results = chunker.chunk_directory(
    "src",
    glob="**/*.py",
    exclude=["**/__pycache__/*"],
    concurrency=4,
)
for result in results:
    if result.error is not None:
        print(result.filepath, result.error)
    else:
        print(result.filepath, len(result.chunks))
```

## Batch and asynchronous calls

`batch(files, concurrency=10, on_progress=None) -> list[BatchResult]` processes
in-memory inputs. Each dictionary contains `filepath` and **`code`**, even for
prose; additional keys are per-item chunking overrides. It does not read those
paths. Results preserve input order, and each failed item has an error string
and an empty chunk list. The optional callback receives
`on_progress(completed, total, filepath)` in completion order. Empty input
returns `[]`; concurrency is clamped to the input count and at least one.

```python
from omnichunk import Chunker

results = Chunker(context_mode="none").batch([
    {"filepath": "a.py", "code": "answer = 42\n"},
    {"filepath": "b.txt", "code": "A short note.", "max_chunk_size": 80},
], concurrency=2)
assert [result.filepath for result in results] == ["a.py", "b.txt"]
assert all(result.error is None for result in results)
```

The async methods keep the same input and result semantics:

| Method | Parameters and result |
| --- | --- |
| `await achunk(filepath, content, **kwargs)` | Runs `chunk()` in the event loop's default thread-pool executor; returns `list[Chunk]` with known totals. `kwargs` are per-call options. |
| `astream(filepath, content, *, buffer_size=8, **kwargs)` | Returns an async iterator with unknown totals. A positive `buffer_size` bounds the output queue and applies producer backpressure. Exceptions reach the consumer. Closing/cancelling iteration cooperatively stops the producer; an active parser/provider call must return before cleanup completes. |
| `await abatch(inputs, concurrency=8)` | Accepts the same `filepath`/`code` dictionaries as `batch()`, limits active calls to at least one, and returns input-ordered `list[BatchResult]`. It has no progress callback. |

```python
from omnichunk import Chunker

async def consume(text: str) -> list[str]:
    chunker = Chunker(max_chunk_size=100, context_mode="none")
    pieces = []
    async for part in chunker.astream("notes.txt", text, buffer_size=2):
        pieces.append(part.text)
    return pieces
```

## Export chunks and prepare embedding batches

The conversion methods accept a `Sequence[Chunk]` and preserve its order. They
prepare data locally; the caller supplies embeddings and performs database I/O.

| Method | Parameters and return value |
| --- | --- |
| `to_dicts(chunks)` | Returns `list[dict[str, Any]]` containing JSON-serializable durable chunk records. |
| `to_jsonl(chunks, output_path=None)` | Returns JSONL as `str`; also writes UTF-8 text when a path is supplied. |
| `to_csv(chunks, output_path=None)` | Returns CSV as `str`; also writes UTF-8 text when a path is supplied. |
| `to_langchain_docs(chunks, *, use_contextualized_text=True)` | Returns LangChain `Document` objects with stable IDs and chunk metadata; requires the `langchain` extra. Set the flag to `False` for raw text. |
| `to_llamaindex_docs(chunks, *, use_contextualized_text=True)` | Returns LlamaIndex `Document` objects with stable IDs and metadata; requires the `llamaindex` extra. The full provenance snapshot is excluded from automatic embedding/LLM metadata rendering. |
| `to_pinecone_vectors(chunks, embeddings, *, namespace="", use_contextualized_text=True)` | Returns legacy vector dictionaries containing `id`, `values` and `metadata`. A nonempty namespace is placed on each row; this shape is not an SDK request. Prefer `chunks_to_pinecone_upsert_request()` for a request envelope and complete metadata preservation. |
| `to_weaviate_objects(chunks, embeddings, *, class_name="OmnichunkDocument", use_contextualized_text=True)` | Returns REST batch objects with deterministic UUIDs, `class`, `vector` and `properties`. For the Python v4 client, pass the UUID, properties and vector explicitly. |
| `to_supabase_rows(chunks, embeddings, *, use_contextualized_text=True)` | Returns insertion dictionaries containing `content`, `embedding` and chunk metadata. |
| `format(chunks, name)` | Calls the named formatter in this chunker's registry and returns its string. An unregistered name raises `ValueError`. |

Vector converters require one nonempty vector per chunk, with consistent
dimensions and finite, float32-representable real values; booleans are rejected.
`use_contextualized_text` selects the exported text; it
does not change embeddings already supplied by the caller. Embed that same text
selection to keep vectors and stored payloads aligned.

```python
from omnichunk import Chunker, PluginRegistry

registry = PluginRegistry()
registry.register_formatter("plain", lambda chunks: "\n".join(c.text for c in chunks))
chunker = Chunker(registry=registry, context_mode="none")
chunks = chunker.chunk("notes.txt", "A useful fact.")
records = chunker.to_dicts(chunks)
jsonl_text = chunker.to_jsonl(chunks)
plain_text = chunker.format(chunks, "plain")
```

`stream_upsert(path, *, embed_fn, adapter="pinecone", batch_size=100, ...)
-> Iterator[UpsertBatch]` combines file iteration, embedding and row conversion.
It accepts one file or a directory. Directory selection uses the same `glob`,
`exclude` and `include_hidden` rules as `chunk_directory()`, but files are
processed sequentially and failures propagate. `encoding` and `**overrides`
apply to each file. `adapter` is `"pinecone"`, `"weaviate"` or `"supabase"`;
`namespace=""` and `class_name="OmnichunkDocument"` configure the corresponding
row converter. Text encoding defaults to `"utf-8"`.

`embed_fn(texts)` must return one vector per input string with finite,
float32-representable real values and the same positive dimension across all
batches. Text is contextualized by default (`use_contextualized_text=True`);
`use_contextualized_text=False` selects raw text for both embedding and export.
Each result contains `adapter`, `rows` and a tuple of the corresponding
`chunks`. `batch_size` must be positive; the final batch can be smaller and a
batch can span files. Output buffering is bounded by the batch size, while the
current document and enumerated paths remain in memory. The method does not
submit rows to a database. Validation, file and provider errors arise during
iteration. See the [indexing guide](../indexing.md) for recoverable delivery with
an `IndexJournal`.

## Semantic chunks, hierarchies and incremental changes

`semantic_chunk(filepath, content, embed_fn, *, window=3, threshold=0.3,
**overrides) -> list[Chunk]` is a shortcut for `chunk()` with `semantic=True`,
the supplied `semantic_embed_fn`, `semantic_window` and `semantic_threshold`.
Pass those settings through the named shortcut parameters rather than repeating
them in overrides. Semantic routing applies to prose content; ordinary routing
still selects engines for code and markup. `window` must be a positive integer
and `threshold` must be finite and between 0 and 1.

The embedding callback receives `list[str]` and returns a two-dimensional float
array with one row per string and a consistent positive dimension. Values must
be finite. Install the `semantic` extra for NumPy support; the caller chooses
and supplies the model. Semantic results still pass through normal sizing,
coverage and context finalization.

```python
import numpy as np
from omnichunk import Chunker

def embed(texts: list[str]) -> np.ndarray:
    # Executable illustration only; replace with a suitable embedding model.
    return np.array([[len(t), t.count(" ") + 1] for t in texts], dtype=float)

chunker = Chunker(max_chunk_size=100, context_mode="none")
chunks = chunker.semantic_chunk(
    "article.txt", "First sentence. Second sentence. Third sentence.", embed,
    window=2, threshold=0.3,
)
print(chunker.semantic_cache_stats())  # {"hits": ..., "misses": ..., "size": ...}
```

`semantic_cache_stats() -> dict[str, int]` returns per-instance embedding-cache
`hits`, `misses` and `size`; all are zero before the cache is used.
`semantic_embed_cache_size=0` disables caching. Cache only deterministic providers
and change the namespace/model/preprocessing revision when their behavior
changes. Reusing an instance lets repeated semantic calls reuse cached vectors.

`hierarchical_chunk(filepath, content, *, levels, size_unit=None, **overrides)
-> ChunkTree` builds finest-to-coarsest levels from canonical text. `levels`
must contain at least two positive sizes in nondecreasing order, such as
`[128, 512, 1024]`; they replace the ordinary minimum/maximum settings. The
instance size unit is used unless supplied explicitly. Token levels use the
configured tokenizer. Nonzero overlap and line overlap are rejected, and
structured suffixes must be loaded before calling this canonical-text API.
Level 0 contains leaves; coarser chunks span consecutive children. The returned
tree exposes `leaves()`, `roots()`, `at_level()`, `parent()`, `children()` and
`to_dict()`.

```python
from omnichunk import Chunker

tree = Chunker(context_mode="none").hierarchical_chunk(
    "guide.txt", "A detailed explanation. " * 60, levels=[128, 512],
)
assert tree.level_count == 2
for leaf in tree.leaves():
    parent = tree.parent(leaf)
    assert parent is not None
```

`chunk_diff(filepath, new_content, *, previous_chunks, **overrides) -> ChunkDiff`
rechunks the new text with the instance registry and effective options, then
compares stable occurrence IDs and embedding fingerprints. `added` contains
chunks to upsert, `removed_ids` contains IDs to delete, and `unchanged` contains
current chunks with unchanged embedding payloads. `updated` is an advisory
subset of `added` for existing IDs whose payload/configuration changed; those
IDs also appear in `removed_ids` for compatibility. Apply deletes before
upserts. Unchanged chunks carry their new location metadata. Duplicate occurrence
IDs in the previous input are rejected.

```python
from omnichunk import Chunker

chunker = Chunker(context_mode="none")
previous = chunker.chunk("policy.txt", "The limit is five.")
diff = chunker.chunk_diff(
    "policy.txt", "The limit is ten.", previous_chunks=previous,
)
print(diff.removed_ids)  # delete these IDs before upserting diff.added
```

## Inspect configuration, quality and propositions

`config_fingerprint() -> str` fingerprints the instance's default configuration,
parser/tokenizer dependency versions and plugin registry. Per-call overrides do
not modify those defaults; each produced chunk records its effective
`config_fingerprint`. Treat this as a configuration identity, rather than a
source revision or embedding-content hash.

`quality_scores(chunks, *, min_chunk_size=None, max_chunk_size=None,
size_unit=None) -> list[ChunkQualityScore]` returns one heuristic score per
chunk in input order. Omitted arguments use instance defaults. Each score
includes `overall`, `entity_integrity`, `scope_consistency`, `size_balance` and
`size_value`. `chunk_stats(chunks, *, size_unit=None) -> ChunkStats` returns the
count, average/minimum/maximum size, selected unit and entity distribution;
empty input yields zero sizes and an empty distribution. These helpers use
stored raw-text counts (`char_count`, `nws_count` or `token_count`), not a fresh
measurement of the rendered payload. Use `metadata["budget"]` for rendered
budget checks. The scores are structural heuristics, not retrieval evaluation.

`extract_propositions(filepath, text, *, mode="heuristic", llm_fn=None,
**overrides) -> list[Proposition]` extracts factual claims without chunking the
text. Heuristic mode needs no provider. For `mode="llm"`, supply
`llm_fn(filepath, text) -> str` returning JSON such as
`{"claims": [{"text": "The limit is five.", "confidence": 0.9}]}`. Claims must
occur verbatim in the source; unmatched claims are skipped and reported with
`UserWarning`. Each proposition has text, a UTF-8 source-byte range, confidence
and metadata. Overrides are validated as chunk options; they do not configure
the extraction heuristic or the provider callback.

```python
from omnichunk import Chunker

chunker = Chunker(context_mode="none")
chunks = chunker.chunk("facts.txt", "The limit is five.")
print(chunker.chunk_stats(chunks))
print(chunker.quality_scores(chunks))
claims = chunker.extract_propositions("facts.txt", "The limit is five.")
```

## Convenience functions

Import these functions directly from `omnichunk` for a single operation. Except
for the optional configured `chunker` accepted by `chunk_diff`, they create a
fresh `Chunker(**options)`, so per-instance semantic caches are not shared across
calls. File selection, encoding and result semantics match the instance methods.

| Function | Return value and method equivalent |
| --- | --- |
| `chunk(filepath, content, **options)` | `list[Chunk]`; equivalent to `Chunker(**options).chunk(filepath, content)`. |
| `chunk_file(path, encoding="utf-8", **options)` | `list[Chunk]`; reads a local file, with encoding also accepted positionally. |
| `chunk_directory(path, *, glob="**/*", exclude=None, concurrency=10, encoding="utf-8", include_hidden=False, **options)` | File-path-sorted `list[BatchResult]` using the same directory filters and per-file error handling. |
| `hierarchical_chunk(filepath, content, *, levels, size_unit="chars", **options)` | `ChunkTree`; unlike the instance method, the explicit function default is character sizing. |
| `chunk_diff(filepath, new_content, *, previous_chunks, chunker=None, **chunker_options)` | `ChunkDiff`; supply either an existing chunker or options for a new one. Passing both raises `ValueError`. |

```python
from omnichunk import chunk

chunks = chunk("example.py", "answer = 42\n", max_chunk_size=128, context_mode="none")
assert chunks[0].total_chunks == len(chunks)
```

::: omnichunk.chunker.chunk

::: omnichunk.chunker.chunk_file

::: omnichunk.chunker.chunk_directory

::: omnichunk.chunker.hierarchical_chunk

::: omnichunk.diff.engine.chunk_diff

## Generated Chunker reference

::: omnichunk.chunker.Chunker

## Related API references

See [indexing and integrations](indexing-api.md) for the local store, recoverable
journal, delivery sinks and framework adapters. See [advanced APIs](advanced.md)
for serialization, identity, loaders and other standalone helpers.
