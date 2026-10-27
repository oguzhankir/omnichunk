# Source, budget and execution contracts

These contracts describe the implementation prepared for the 2.0 transition and
2.1 code-quality release. They do not announce a published package. See the
[migration guide](../migrations/v2.md) before replacing an existing index.

## Configuration and size

`Chunker` validates constructor options and per-call overrides. Unknown names,
internal `_precomputed_*` arguments and invalid combinations raise errors.
`ChunkOptions` is frozen; create another configuration instead of mutating it.

| Option | Default | Meaning |
| --- | --- | --- |
| `max_chunk_size` | `1500` | Limit measured against the final rendered payload. |
| `min_chunk_size` | `50` | Packing preference, not a guaranteed lower bound. |
| `size_unit` | `"chars"` | Unicode characters; alternatively `"nws"` or `"tokens"`. |
| `tokenizer` | `None` | Required for token sizing; named tokenizer or counting callable. |
| `coverage_policy` | `"retrieval"` | Omit whitespace-only output; `"lossless"` retains all source bytes. |
| `overflow_policy` | `"split"` | Split oversized spans; alternatives are `"error"` and `"preserve"`. |
| `context_overflow` | `"omit"` | If added context cannot fit, emit raw text and retain structured metadata; `"error"` rejects it. |
| `context_mode` | `"full"` | Render structural context; alternatives are `"minimal"` and `"none"`. |
| `algorithm_version` | `"2.1"` | Recorded behavior version; no other algorithm version is currently implemented. |

When only a smaller `max_chunk_size` is supplied, `Chunker` reduces its default
minimum to fit. An explicitly supplied minimum greater than the maximum is invalid.
`preserve_decorators`, `preserve_comments` and `include_header_in_sections` retain
their `True` compatibility values; setting them to `False` raises an error.
The unused `semantic_threshold_k` and `semantic_window_size` options were removed.

```python
from omnichunk import Chunker

chunker = Chunker(max_chunk_size=80, context_mode="none")
chunks = chunker.chunk("example.txt", "Merhaba dünya. " * 20)
assert all(len(chunk.contextualized_text) <= 80 for chunk in chunks)
assert all(chunk.metadata["budget"]["overflow"] == 0 for chunk in chunks)
```

For model tokens, install the matching tokenizer extra and pass its name, for
example `Chunker(size_unit="tokens", tokenizer="cl100k_base")`. A custom callable
must return a nonnegative integer count for the supplied string. Exactness then
depends on that callable matching the tokenizer used downstream. Unknown named
tokenizers raise errors; they do not silently become word counters.
`tokenizer="approximate"` explicitly opts into estimates. With character/NWS
sizing and no tokenizer, `token_count` is also an estimate, not a model guarantee.

Every finalized chunk has `metadata["budget"]` with `unit`, `limit`, rendered
`size`, `raw_size`, `overflow`, `policy`, `token_accuracy` and
`rendered_token_count`. `metadata["context_omitted"]` records omitted rendered
context. `context_overflow="omit"` does not erase `Chunk.context`.

`overflow_policy="preserve"` explicitly permits oversized payloads and reports
the excess plus `metadata["overflow_reason"]`. Strict splitting prefers fitting
declarations and lexical boundaries but can divide an oversized definition;
intersecting entity metadata is marked `is_partial`. A unit that cannot fit even
as one Unicode character raises `ChunkingError` in strict mode.

Fitting documented root statements retain their leading and same-line trailing
comments as one unit. Independent documented statements keep separate boundaries;
oversized groups use the normal recursive fallback. A complete code file that
fits the maximum retains its existing single-chunk behavior.

Inside an oversized declaration, complete body statements can use the remaining
budget beside their declaration header. Pending source from a different
declaration is flushed before descending into that declaration, preserving its
own scope and sibling context.

`code_boundary_policy="compact"` optionally compares AST, measured-prefix,
line-preferred and balanced-size layouts for oversized code. It selects fewer
fragments first, then fuller earlier measured payloads. Alternative layouts do not
divide fitting definitions or documented root groups, but may divide statements
or expressions inside oversized declarations. This trades finer source structure
for fewer vectors and more surrounding code in each payload; evaluate both
retrieval quality and index cost. Source slices and final payload budgets remain
checked. The default is `"structure"`; `error` and `preserve` overflow policies
retain their existing behavior.

Compact layout selection is a bounded comparison of measured candidates, not an
exhaustive search over all possible cuts. When no inspected candidate satisfies
the budget without dividing a protected definition, it raises `ChunkingError`
instead of silently discarding that protection. This can occur with nonadditive
custom counters. Use `code_boundary_policy="structure"`, increase the budget, or
review the counter's model-token accounting.

With `overflow_policy="split"`, an oversized comment-and-statement group can
split at a comment sentence boundary when both complete resulting source slices
fit. This keeps the remaining comment text beside its statement and includes
same-line trailing comment chains in the check. Chunk text is a source slice;
a slice beginning within a comment is not necessarily independently executable.
The `error` and `preserve` policies do not apply this rebalance.

Prose and Markdown split oversized content in structural order: paragraphs,
lines (including table rows), sentences, semicolon clauses, whitespace, then
smaller separators and measured character prefixes. Prose sentence fallback
avoids heuristic endpoints inside matched, unescaped square brackets without
changing the public semantic sentence splitter. A unit that fits keeps its
boundary; oversized units descend to the next level. Source whitespace
participates in the measured budget.

Markdown keeps blank-line-separated body paragraphs distinct and associates
headings with their following content by default. Set
`markdown_paragraph_policy="pack"` to combine adjacent fitting prose paragraphs
under the same heading. This can reduce vector count while adding less relevant
context to a chunk; evaluate the quality/cost tradeoff for your retriever.
Pipe-delimited table blocks and list
blocks retain their own section identities instead of classifying surrounding
prose as part of a table or list. Blank-separated list items and sufficiently
indented continuation paragraphs keep their list ownership; dedented following
prose starts a separate paragraph. This applies in both paragraph policies, so
list continuations are not eligible for prose packing. Even a small Markdown file that fits the
maximum can therefore produce multiple chunks. `min_chunk_size` is a preference:
it does not merge these paragraph identities back together, and a short heading
or tail can remain below the minimum. This can increase vector/index work and
reduce adjacent context; it is not a universal cost or quality improvement.
Table headers are not repeated as derived context by this policy.

The default sentence heuristic recognizes Unicode uppercase/uncased starters and
Japanese/Chinese `。！？` without intervening spaces. Closing quotes and whitespace
remain with the preceding sentence. Abbreviations and ambiguous linguistic
boundaries still need a custom `semantic_sentence_splitter` in semantic mode; that callback
must preserve all source characters. Changing boundaries changes chunk IDs:
rechunk affected documents and apply deletions when updating an existing index.

## Source coordinates and coverage

- `Chunk.text` is an exact slice of its declared canonical source.
- `byte_range` is a zero-based, half-open UTF-8 interval: `[start, end)`.
- `line_range` is zero-based and inclusive; a trailing newline belongs to its
  preceding line. Entity and scope coordinates use the same canonical source.
- `contextualized_text` is derived text and has no source-slice guarantee.
- `SourceDescriptor` records `source_id`, canonical-text SHA-256 `revision`,
  `encoding`, `normalization`, `format_name` and loader metadata.

For ordinary strings, `source_id` defaults to the filepath label. Supply a stable
logical ID when filename changes should not change identity. File APIs decode the
file before chunking; binary container bytes are not the canonical text.

```python
from omnichunk import Chunker

source = "Türkçe 你好\n\nSecond paragraph.\n"
result = Chunker(
    max_chunk_size=24,
    context_mode="none",
    coverage_policy="lossless",
).chunk_with_manifest("example.txt", source, source_id="guide:introduction")
raw = source.encode("utf-8")
assert not result.skipped_ranges
assert b"".join(chunk.text.encode("utf-8") for chunk in result.chunks) == raw
for chunk in result.chunks:
    assert raw[chunk.byte_range.start:chunk.byte_range.end].decode("utf-8") == chunk.text
```

`chunk_with_manifest()` returns `ChunkResult(source, chunks, skipped_ranges,
diagnostics)`, including omissions when retrieval output is empty. It accepts
canonical text with an ordinary text filepath, not `.ipynb`, `.tex`, `.rst`,
`.pdf` or `.docx` container paths. Direct concatenation reconstructs a lossless
partition only when numeric overlap is disabled. With overlap, use the union of
ranges; repeated bytes must not be counted twice.

Structured loaders produce `LoadedDocument.text` and character-indexed segments.
`chunk_loaded_document(filepath, loaded, options)` applies the same final source
and budget checks to an explicitly loaded document.
Notebook, PDF and DOCX chunk offsets refer to that extracted text, not JSON or
binary bytes. Preserve page/cell/element metadata for citations. See the notebook
reconstruction example in the [migration guide](../migrations/v2.md).
Malformed notebooks raise `ChunkingError` when chunked. Nonfatal loader warnings
reach `context.parse_errors` and the source descriptor's warning metadata.

## Overlap and iteration

`overlap=20` requests overlap measured in the configured size unit;
`overlap=0.1` requests a fraction of `max_chunk_size`. It repeats raw source spans,
and exact payload limits still apply. The actual retained overlap can be smaller
when the budget cannot accommodate both overlap and new source text.

`overlap_lines=1` adds preceding lines to derived context only. Raw chunk ranges
retain their ordinary coverage behavior. It may be omitted under the context
budget policy. Nonzero numeric overlap and line overlap cannot be combined.

`chunk()` and `stream()` share finalization and supported options. `chunk()`
returns a list with known `total_chunks`; `stream()` yields `total_chunks=-1`.
`stream_file()` still reads source content; its name describes output iteration.

| Execution path | Resident data and output buffering |
| --- | --- |
| Ordinary code/prose/markup/hybrid | Complete source, UTF-8/NWS indexes, parser/window structures, occurrence-ID bookkeeping; output chunks are yielded. |
| Semantic | Sentence/window embeddings and candidate chunks can be retained for the document. |
| Structured documents | Canonical extracted text and segments remain resident; some loaders retain per-document candidates/results. PDF/DOCX `stream_file()` currently buffers the file's chunk list. |
| `astream(buffer_size=8)` | Above engine state plus a bounded output queue; producer backpressure and cooperative cancellation. A running parser/provider call must return before cleanup completes. |
| `stream_upsert(batch_size=100)` | Above per-document state plus a bounded chunk/embedding batch and enumerated file paths. The caller writes returned rows to its database. |
| `batch()` / `abatch()` | Concurrent per-file work; returned results remain in input order and are collected. |

No path promises constant total memory. Bound concurrency and document size for
large corpora; asynchronous wrappers do not make CPU parsing parallel without cost.

## Identity, persistence and embedding invalidation

`stable_chunk_id()` combines logical source identity, the raw text hash and its
source-order occurrence among equal chunks. Position and configuration are excluded.
A byte-identical block can retain its ID after movement; repeated equal blocks
can change occurrence numbers after insertions. This is not a general rename/move
matching engine. Preserve `source_id` explicitly to preserve document identity.

`chunk_embedding_fingerprint()` in `omnichunk.serialization` includes raw text,
rendered context and configuration fingerprint. Indexing clients must additionally
version the embedding model they use outside the chunker. `chunk_diff()` reports
same-ID payload changes in `updated`, which is a subset of `added`; those IDs also
appear in `removed_ids`. Apply deletes before upserts. Refresh location metadata
for `unchanged` chunks without re-embedding unchanged payloads.

Versioned JSON preserves every documented `Chunk` and `ChunkContext` field.
Legacy/unversioned JSON remains readable; unsupported schemas are rejected.
`ChunkStore(path, collection="default")` returns source-ordered chunks and commits
a complete sync atomically. Deletion is limited to missing files owned by a
previous completed scan with the same root and filters. Partial/new scans do not
delete unrelated data. Failed reads/parses/providers/writes roll back the sync.
The write transaction spans processing; large syncs can hold the write lock.

Persisted skips require known callback identities. Give custom callbacks a stable
`fingerprint` attribute, or semantic providers both `semantic_cache_namespace` and
`semantic_model_revision`; otherwise the store conservatively reprocesses files.
Use `PluginRegistry(revision="your-parser-v1")` with versioned custom parsers.
Change these identities when implementation, model or preprocessing changes.

The semantic embedding cache separately isolates provider objects, namespace,
model revision and preprocessing. It serializes cache misses under a lock and
validates vector shape, finite values and dimensions. Cache only providers whose
outputs are reproducible under the declared identity.

## Parsers, plugins and tool serving

For Python, documentation-heavy automatic routing counts only real module, class,
function and async-function docstrings identified by the standard-library AST.
Their original literal source must occupy more than 40% of the file's UTF-8 bytes
to select hybrid processing. Assigned/returned SQL, templates and other string
data do not contribute. A parse failure leaves this heuristic on the code route,
where parser diagnostics and fallbacks remain available. Explicit content-type
overrides and notebook/cell markers select their routes independently.

`language_capabilities()` lists detected code languages, extensions, grammar
registration/loading, parser availability, bundled query availability and effective
extraction (`ast`, `regex` or `none`). Query availability is not proof of complete
language coverage. Install `omnichunk[code]` for the six primary grammars and
`omnichunk[all-languages]` for the full registered grammar set, including the primary six.

`Chunker(registry=PluginRegistry())` uses an explicit plugin scope. Legacy global
registrations are snapshotted when a chunker is constructed. Parser failures are
reported in `context.parse_errors`; `context.format_metadata["parser_backend"]`
identifies the selected code parser/fallback.

`omnichunk serve --rpc --allowed-root ./project` starts the experimental HTTP
JSON-RPC service. `--mcp` remains a deprecated alias; MCP lifecycle and tool
discovery are not implemented. The server validates resolved file roots, Host and
Origin, request sizes and read timeouts. Non-loopback binding requires a bearer
token; `--token-env` names its environment variable. It uses stdlib `HTTPServer`,
without TLS or hard cancellation of an executing parser. A real MCP adapter
remains future work.


### Compact prose fallback

`prose_boundary_policy="sentence"` is the default and keeps fitting sentence units
intact during oversized prose splitting. For a denser index, explicitly choose
`prose_boundary_policy="compact"`. This also tries clause/word fallback and selects
it when the resulting partition has equal or fewer fragments. A sentence that
would fit on its own may be divided. Existing paragraph, fence and heading
boundaries remain governed by their own policies; fitting paragraphs are not
changed. Complete source slices and measured payload budgets remain enforced.
Evaluate retrieval and vector counts for the selected mode; compact output does
not imply universally better retrieval or a minimum fill ratio. The option is
part of the configuration fingerprint, so rebuild persisted index generations
when adopting it.
