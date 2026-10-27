# Advanced APIs

These helpers support structured document loading, semantic processing and
retrieval pipelines around the [chunking API](chunker.md). Signatures and defaults
below are generated from source. The [source and budget contracts](contracts.md)
define canonical text, coordinates and payload limits; the
[indexing API](indexing-api.md) covers persistent stores and backend delivery.

Most names are available from `omnichunk`. Import helpers documented with a
module-specific path from that module, for example
`from omnichunk.formats import load_rst`.

## Structured document formats

Loaders return `LoadedDocument(text, segments, format_name, warnings)`. Its `text`
is the canonical source for subsequent chunks. `FormatSegment.char_start` and
`char_end` are half-open **character** offsets into that string; finalized
`Chunk.byte_range` values are half-open **UTF-8 byte** offsets. PDF, DOCX and
notebook coordinates therefore refer to extracted text, not container bytes.
Preserve `context.format_metadata` for page, cell or document-element citations.

Pass `filepath`, a loaded document and a `ChunkOptions` instance to
`chunk_loaded_document()`. The filepath supplies a source label; `options`
controls the same size, context, overlap and overflow policies as ordinary
chunking. Loader warnings are carried into source metadata and chunk parse errors.
An empty result with loader warnings raises `ChunkingError` when chunked.

| Loader | Input and behavior |
| --- | --- |
| `load_ipynb` | Notebook JSON string; `include_outputs=False` excludes outputs. Enabling it includes textual stream, error and plain-text display output, not binary images. Invalid JSON/cells produce loader warnings. |
| `load_pdf_bytes` | PDF bytes; requires `omnichunk[pdf]`. Extracts page text with page metadata; it does not perform OCR. |
| `load_docx_bytes` | DOCX bytes; requires `omnichunk[docx]`. Extracts paragraphs and tables in document order. |
| `load_latex` | LaTeX source string; retains source syntax and identifies prose, code environments and supported math regions. It does not compile TeX. |
| `load_rst` | reStructuredText source string; identifies prose and code directives without `docutils`. It does not resolve external `literalinclude` files. |

```python
from pathlib import Path

from omnichunk import ChunkOptions, chunk_loaded_document, load_ipynb

loaded = load_ipynb(Path("analysis.ipynb").read_text(encoding="utf-8"))
chunks = chunk_loaded_document(
    "analysis.ipynb", loaded,
    ChunkOptions(max_chunk_size=800, context_mode="none"),
)
```

::: omnichunk.formats.FormatSegment

::: omnichunk.formats.LoadedDocument

::: omnichunk.formats.chunk_loaded_document

::: omnichunk.formats.load_ipynb

::: omnichunk.formats.load_pdf_bytes

::: omnichunk.formats.load_docx_bytes

::: omnichunk.formats.load_latex

::: omnichunk.formats.load_rst

## Semantic splitting and reranking

Install `omnichunk[semantic]` for NumPy-based helpers. Embedding providers are
caller-supplied; `get_local_embedder()` additionally requires
`omnichunk[sentence-transformers]` and loads its selected model on the first
embedding call. Creating the provider checks that the dependency is installed.
Model selection and any model download remain the caller's responsibility.

`split_sentences(text)` returns `(sentence_text, char_start, char_end)` triples
that cover the source contiguously. Its default is a language heuristic.
A custom `splitter_fn` must return strings that reconstruct the entire source,
including whitespace, in order; a splitter that strips whitespace is rejected.

For `detect_semantic_boundaries()`, supply an `embed_fn` returning an `(N, D)`
array for the `N` input windows, one row per window. `window` counts sentences
around each position. A boundary is proposed when adjacent-window similarity is
below `threshold` **or** is a strict local minimum; it is not solely a threshold
filter. `min_chunk_sentences` constrains semantic groups on both sides.
`SemanticBoundaryResult.boundary_indices` gives the sentence indices **after**
which to split. `SemanticSplitter.split(filepath, text, options)` then applies
shared source and budget finalization; size limits can divide semantic groups
further. Use positive windows and minimum sentence counts.

::: omnichunk.semantic.sentences.split_sentences

::: omnichunk.semantic.boundaries.detect_semantic_boundaries

::: omnichunk.semantic.boundaries.SemanticBoundaryResult

::: omnichunk.semantic.splitter.SemanticSplitter

::: omnichunk.semantic.embedders.get_local_embedder

### TF-IDF and topic shifts

`build_tfidf_matrix(documents)` returns a dense, L2-normalized matrix with one row
per input document. `max_vocab` limits vocabulary size; `min_df` is the minimum
number of documents containing a token. For larger collections,
`build_tfidf_sparse()` returns a SciPy CSR matrix when SciPy is installed and
falls back to a dense NumPy array otherwise. Install `omnichunk[scipy]` when the
sparse return type is required.

`detect_topic_shifts()` compares mean TF-IDF vectors on each side of a sentence
gap. `window_size` overrides the legacy `window` width. `method="fixed"` uses
`threshold`; `method="adaptive"` uses the document's mean similarity minus
`k` standard deviations. `min_shift_gap` spaces accepted boundaries apart.
`return_scores=True` returns `(shift_indices, scores)` with one similarity per
gap, useful for inspecting a chosen policy. These are lexical heuristics and do
not require an embedding model.

::: omnichunk.semantic.tfidf.build_tfidf_matrix

::: omnichunk.semantic.tfidf.build_tfidf_sparse

::: omnichunk.semantic.tfidf.detect_topic_shifts

### Diversity and embedding caches

`rerank_chunks()` selects up to `top_k` candidates by maximal marginal relevance.
Provide a query vector of dimension `D` and an `(N, D)` embedding matrix aligned
with the `N` chunks. Inputs are normalized internally. Choose `lambda_` between
`0` and `1`: `1` emphasizes query relevance, while `0` favors diversity after the
first, most relevant choice. Ties use input order. This function selects from
existing candidates; it neither embeds text nor enforces a context budget.

`EmbeddingCache(max_size=4096).wrap()` caches deterministic provider outputs.
Provider identity, optional `namespace`, `model_revision` and `preprocessing`
partition cached entries. Change those identities or clear the cache when model
behavior changes. Misses, including provider calls, are serialized under a lock;
`stats()` exposes hits, misses and resident entries.

::: omnichunk.semantic.rerank.rerank_chunks

::: omnichunk.semantic.cache.EmbeddingCache

## Entity graphs

`build_chunk_graph(chunks)` connects chunks sharing names in
`chunk.context.entities`. Graph indices are positions in the supplied sequence,
not necessarily the chunks' own `index` fields. `min_entity_occurrences=2`
requires an entity to occur in at least two distinct chunks; `ignore_types`
excludes import/export entity types by default. Names are matched as strings, so
use a suitable document scope when unrelated symbols share names. This graph
does not infer calls or dependencies from source text.

`ChunkGraph` stores entity nodes and shared-entity edges, with lookup methods and
`to_dict()` / `from_dict()` conversion. Analytics treat edges as undirected.
`compute_centrality()` uses unweighted shortest paths; `find_communities()` uses
weighted, deterministic label propagation. These pure-Python routines target
small graphs (roughly fewer than 500 chunks). `to_networkx_dict()` exports
node-link data with `nodes` and `links` keys for further analysis; NetworkX is
optional and is not imported by these helpers.

::: omnichunk.graph.build_chunk_graph

::: omnichunk.graph.ChunkGraph

::: omnichunk.graph.EntityNode

::: omnichunk.graph.ChunkEdge

::: omnichunk.graph.compute_centrality

::: omnichunk.graph.find_communities

::: omnichunk.graph.to_networkx_dict

## Language capabilities, deduplication and tracing

`language_capabilities()` returns a `LanguageCapability` for each supported code
language. It reports file extensions, grammar registration and availability,
parser and query availability, extraction mode (`"ast"`, `"regex"`, or `"none"`),
and the grammar module when registered. A bundled query does not imply exhaustive
syntax support; check chunk diagnostics for input-specific parse errors.

`dedup_chunks(chunks, *, method="simhash", threshold=0.85)` returns the kept
chunks and a mapping from removed chunk indexes to kept indexes. `method` accepts
`"exact"`, `"simhash"`, or `"minhash"`; the approximate methods use `threshold`
as a similarity cutoff and candidate bucketing, so they can miss near duplicates.
Use unique chunk indexes in the input when interpreting the mapping.

`maybe_span(tracer, name, **initial_attrs)` is a context manager for an optional
OpenTelemetry-compatible tracer. `name` names the span and keyword arguments
become initial attributes; a missing tracer yields `None` without opening a span.

::: omnichunk.parser.languages.LanguageCapability

::: omnichunk.parser.languages.language_capabilities

::: omnichunk.dedup.dedup_chunks

::: omnichunk.otel.util.maybe_span

## Retrieval and chunk evaluation

Ranking and evidence metrics answer different questions. `score_ranking()`
compares ordered passage IDs with explicit relevance grades. `k` is a positive
integer cutoff, and grades must be finite and nonnegative. Unjudged IDs have
zero relevance. Positive judgments define recall's denominator; nDCG uses graded
exponential gains and an ideal ranking from all judgments. Repeated IDs consume
rank slots without repeated credit. With no positive judgments, all ranking
scores are zero.

`score_evidence()` compares unions of `EvidenceSpan(source_id, start, end)` values
using half-open UTF-8 byte coordinates. Matching IDs must identify the same
canonical source revision; the span class validates coordinates, not the actual
source bytes. Overlapping ranges count once, and ranges from different sources
never match. Precision, recall and intersection-over-union are byte-weighted.
Both sets empty yields all ones; only one set empty yields all zeros. Neither
ranking nor evidence metrics measures generated answer correctness.

::: omnichunk.retrieval_eval.score_ranking

::: omnichunk.retrieval_eval.RankingMetrics

::: omnichunk.retrieval_eval.EvidenceSpan

::: omnichunk.retrieval_eval.score_evidence

::: omnichunk.retrieval_eval.EvidenceMetrics

### Offline chunk diagnostics

`evaluate_chunks(chunks, source=None, metrics="all")` returns an `EvalReport`
with per-chunk and aggregate values. Supply the exact canonical `source` for
`reconstruction` and `coverage`; these values are otherwise `None`. Aggregate
coverage measures the union of correctly reconstructed byte ranges, so overlap
does not earn duplicate coverage. `density` uses non-whitespace character counts.
`coherence` and `boundary_quality` are TF-IDF sentence heuristics requiring NumPy,
not retrieval scores or learned quality judgments. Select a sequence of metric
names to avoid unwanted work; unknown names raise `ValueError`. Unavailable or
unrequested values are `None`. `eval_report_to_dict()` produces a plain mapping.

::: omnichunk.eval.evaluate_chunks

::: omnichunk.eval.ChunkEvalScores

::: omnichunk.eval.EvalReport

::: omnichunk.eval.eval_report_to_dict

## Context budget selection

`TokenBudgetOptimizer(budget, ...)` selects existing chunks without splitting
them. `scores` passed to `select()` must align with the chunks; omitted scores
are all `1`. `strategy="greedy"` visits chunks in descending score order, while
`strategy="dp"` maximizes total score within the budget using knapsack selection.
The latter falls back to greedy when `len(chunks) * budget` exceeds 50 million.
`preserve_order=True` sorts selected chunks by starting byte offset; this is
source-local ordering, not a cross-document ranking.

`size_unit` accepts `"tokens"`, `"chars"` or `"nws"` and measures rendered
`contextualized_text`. Token sizing uses recorded `rendered_token_count`; manual
contextualized chunks lacking that metadata are rejected. Raw-only manual chunks
can use `token_count`, whose accuracy depends on how it was populated.
`BudgetResult.total_tokens` uses the selected unit despite its field name.
`deduplicate_overlap=True` removes lower-scored similar text using token-set
Jaccard similarity and `overlap_threshold`; it does not compare source ranges.

The optimizer adds individual chunk sizes. Reserve room for prompts, separators
and citations, and measure the final joined context with the downstream tokenizer:
token counts need not be additive across joins. Selection does not establish a
complete model-input guarantee.

::: omnichunk.budget.TokenBudgetOptimizer

::: omnichunk.budget.BudgetResult

## Parser and formatter plugins

Use `PluginRegistry(revision="my-parser-v1")` and pass it as `registry=` to
`Chunker` for an explicit pipeline scope. A parser callback receives
`(filepath, content)` and returns a tree-like object or `None`; a formatter
receives a chunk sequence and returns a string. Register these through the
registry's `register_parser()` and `register_formatter()` methods, and call
`chunker.format(chunks, name)` to use a formatter. Change `revision` when plugin
behavior changes so persisted configuration identities can change with it.

Legacy module-level registration is global. A `Chunker` constructed without an
explicit registry snapshots those registrations at construction; later global
registrations do not alter that chunker. Language names are stripped and
lowercased; formatter names are stripped and case-sensitive. Duplicate names
raise `ValueError` unless `overwrite=True`. Module-level listing functions return
sorted global names, rather than inspecting a particular chunker's registry.

::: omnichunk.plugins.PluginRegistry

::: omnichunk.plugins.register_parser

::: omnichunk.plugins.register_formatter

::: omnichunk.plugins.list_registered_parsers

::: omnichunk.plugins.list_registered_formatters

## Serialization and export

Use `chunk_to_dict()` / `chunk_from_dict()` for complete versioned chunk records,
including context, source identity and metadata. The reader accepts legacy v1
and unversioned records and rejects unsupported schema versions.
`chunks_to_jsonl()` returns these records as JSON Lines; `output_path` optionally
writes UTF-8 output. `chunks_to_csv()` flattens a selected set of fields for
inspection and is not a complete round-trip format.

`stable_chunk_id()` identifies a content occurrence within a logical source;
`filepath` explicitly overrides that source identity when supplied.
`chunk_content_fingerprint()` hashes raw UTF-8 text, while
`chunk_embedding_fingerprint()` includes rendered text and chunk configuration.
Track the embedding model revision separately. See the
[identity contracts](contracts.md#identity-persistence-and-embedding-invalidation)
before replacing an existing index.

::: omnichunk.serialization.chunk_to_dict

::: omnichunk.serialization.chunk_from_dict

::: omnichunk.serialization.chunks_to_jsonl

::: omnichunk.serialization.chunks_to_csv

::: omnichunk.serialization.stable_chunk_id

::: omnichunk.serialization.chunk_content_fingerprint

::: omnichunk.serialization.chunk_embedding_fingerprint

### Framework documents and vector payloads

Framework converters require the corresponding LangChain or LlamaIndex extra.
`use_contextualized_text=True` selects rendered content; choose `False` for raw
source text. Both retain a complete serialized chunk snapshot in document
metadata. For native pipeline adapters, see the [indexing API](indexing-api.md).

Vector payload converters return dictionaries without writing to a service or
computing embeddings. Supply one nonempty vector per chunk in the same order,
with a consistent dimension and finite float32-representable real values.
Set `use_contextualized_text` to match the text actually embedded.

Prefer `chunks_to_pinecone_upsert_request()` for a Pinecone request envelope.
`namespace` belongs on that envelope. Aligned `filter_metadata` entries add flat
queryable fields; generated-name collisions, unsupported values and metadata
larger than `max_metadata_bytes` fail explicitly. The legacy
`chunks_to_pinecone_vectors()` per-vector namespace shape is not an SDK request.
`chunks_to_weaviate_objects()` emits REST batch objects; with the Python v4 client,
pass each object's `id` as `uuid` and its properties/vector explicitly.
`weaviate_object_id()` converts stable chunk IDs for matching deletions.
`chunks_to_supabase_rows()` returns insert-ready row dictionaries; the caller
owns the database schema and writes.

::: omnichunk.serialization.chunks_to_langchain_docs

::: omnichunk.serialization.chunks_to_llamaindex_docs

::: omnichunk.serialization.chunks_to_pinecone_upsert_request

::: omnichunk.serialization.chunks_to_pinecone_vectors

::: omnichunk.serialization.chunks_to_weaviate_objects

::: omnichunk.serialization.weaviate_object_id

::: omnichunk.serialization.chunks_to_supabase_rows
