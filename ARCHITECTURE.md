# Architecture

This documents the implementation prepared for the 2.0 contract transition and
2.1 code-quality release. Publication and remaining release gates are tracked in
[ROADMAP.md](ROADMAP.md). Public behavior and upgrade workflows are described in
[contracts](docs/reference/contracts.md) and [migration](docs/migrations/v2.md).

## Pipeline and routing

[`Chunker`](src/omnichunk/chunker.py) provides text, file, directory, batch,
iterator, asynchronous, diff, hierarchy and export entry points. A chunker owns
validated defaults, a plugin registry snapshot and its semantic embedding cache.

1. [`config.py`](src/omnichunk/config.py) validates frozen `ChunkOptions`, merges
   public overrides and fingerprints output-affecting options and dependencies.
2. [`TextIndex`](src/omnichunk/util/text_index.py) maps canonical text between
   Unicode positions, UTF-8 bytes and lines; NWS prefix counts support packing.
3. [`engine/router.py`](src/omnichunk/engine/router.py) detects language/content
   type and selects an engine that proposes source spans and structural context.
4. [`finalize.py`](src/omnichunk/finalize.py) checks source slices, fills lossless
   gaps, applies overlap, measures rendered payloads and splits/rejects/reports
   overflow. It attaches source descriptors, occurrence numbers and budget metadata.
5. `stream()` yields finalized chunks with unknown totals; `chunk()` collects the
   same output and sets totals. Structured-document entry points also finalize.

| Engine | Candidate boundaries and metadata |
| --- | --- |
| [`CodeEngine`](src/omnichunk/engine/code_engine.py) | Tree-sitter or deterministic fallback entities, scope/import/sibling context and NWS-packed windows. |
| [`ProseEngine`](src/omnichunk/engine/prose_engine.py) | Paragraphs, Markdown headings, lists, tables and fenced code; fence contents delegate to code/markup engines. |
| [`MarkupEngine`](src/omnichunk/engine/markup_engine.py) | JSON, YAML, TOML, HTML/XML parsing or structural heuristics. |
| [`HybridEngine`](src/omnichunk/engine/hybrid_engine.py) | Code/prose segments derived from cell markers and docstring heuristics. |
| [`SemanticEngine`](src/omnichunk/engine/semantic_engine.py) | Embedding-window boundaries when semantic mode is enabled for prose. |

Semantic mode is selected for prose rather than applied universally to every
engine. Structured loaders route their code/prose segments explicitly.

## Coordinates, context and budgets

`Chunk.text` is a literal slice of its declared canonical text. Chunk, entity and
scope ranges use zero-based, half-open UTF-8 byte offsets and inclusive zero-based
line numbers. [`context/rebase.py`](src/omnichunk/context/rebase.py) moves nested
segment metadata into document coordinates. Internal Markdown `ProseNode` ranges
remain character-indexed and are converted before exposing chunk metadata.

[`formats/`](src/omnichunk/formats/) loads Jupyter, LaTeX, reStructuredText, PDF
and DOCX into `LoadedDocument(text, segments, format_name, warnings)`. Segments
use character indices in extracted canonical text. Offsets never claim to address
notebook JSON or PDF/DOCX binary bytes; page/cell/element metadata supports citations.
Warnings propagate to chunk diagnostics and source metadata; unusable malformed
input raises an error instead of appearing to be an empty successful document.

`SourceDescriptor` records logical source identity, the canonical UTF-8 SHA-256,
encoding, extraction/decoding normalization and format. Ordinary file reads preserve
line endings. `chunk_with_manifest()` exposes source coverage and diagnostics for
canonical ordinary text; container paths use loaders and their canonical text.

The default unit is Unicode characters. Token budgets require an explicit tokenizer
or counting callable; approximate token counting is labeled. The shared finalizer
measures `contextualized_text`, including derived context and overlap. It preserves
structured context when rendering must be omitted, and marks intersected entities
partial after splitting. `preserve` overflow is an explicit, recorded exception.

Retrieval coverage omits whitespace-only output; lossless coverage retains it.
Numeric overlap repeats raw source spans under the payload limit; `overlap_lines`
adds derived context. Combining nonzero numeric and line overlap is invalid.

## Parsing and optional dependencies

The base install has no mandatory third-party dependencies. The `code` extra adds
Tree-sitter and six primary grammars; additional grammars, NumPy semantic helpers,
named tokenizers, binary loaders, embedding models and framework adapters are extras.
The Rust extension remains optional.

[`language_capabilities()`](src/omnichunk/parser/languages.py) distinguishes
filename detection, grammar registration/loading, parser/query availability and
AST/regex/no extraction. A registered language is not proof of complete syntax
support. Parsers are thread-local; plugin/grammar failures fall back deterministically
and expose reasons plus `parser_backend` metadata. Entity lookup uses a sorted
range sweep instead of scanning every entity for every emitted code window.

[`PluginRegistry`](src/omnichunk/plugins.py) provides isolated parser/formatter
registrations using context-local execution. Legacy global registrations are
snapshotted at chunker creation. Persisted custom parsers need a registry revision.

## Identity, persistence and integrations

[`serialization.py`](src/omnichunk/serialization.py) emits schema-versioned complete
chunk/context records and reads legacy records. Stable IDs combine source identity,
raw-content hash and duplicate occurrence. Embedding fingerprints additionally
include rendered text and configuration. Diffing still performs full rechunking;
changed same-ID payloads are present in both `updated` and `added`.

[`ChunkStore`](src/omnichunk/store/chunk_store.py) uses SQLite collections with
source-ordered reads, configuration-aware skips and atomic complete-scan commits.
Deletion is scoped to prior completed scans with matching roots/filters; errors
roll back. Separate-path legacy migration preserves the old store and requires
reindexing. Transaction locks span processing, so sync is not a distributed indexer.

[`semantic/`](src/omnichunk/semantic/) provides sentence splitting, provider-based
embeddings, caching, TF-IDF, topic shifts and reranking. Cache keys isolate provider,
namespace, model revision and preprocessing; locks and vector validation protect
shared batch use. No remote provider is called without caller configuration.

Hierarchy, token-budget selection, graphs, propositions and deduplication remain
optional helpers. Framework/vector exports produce payloads; callers perform remote
writes. Their presence does not establish superior retrieval quality.

The experimental [`JSON-RPC server`](src/omnichunk/mcp/server.py) validates resolved
file roots, Host/Origin, authentication where required, request sizes and read
timeouts. `--rpc` is the primary flag; deprecated `--mcp` does not implement MCP
initialization or tool discovery. Stdlib HTTP serving has no TLS or hard cancellation
of parser execution, and semantic RPC uses a mock embedder.

## Execution limits and validation

Streaming retains complete source text, indexes, parsing/window structures and
occurrence bookkeeping. Semantic processing can retain embeddings/candidates;
structured loading retains canonical text and segments. PDF/DOCX `stream_file()`
currently buffers the final list. `astream()` bounds its output queue and cooperates
with cancellation; an active parser/provider must finish before cleanup completes.
`stream_upsert()` bounds output/embedding batches, while batch APIs collect results.
None of these paths promises constant total memory.

Tests cover exact source slices, final payload bounds, Unicode/nested scopes,
fallbacks, iterator parity, identity, serialization, store rollback and server
boundaries. Slow property tests require an explicit pytest marker override.
Benchmarks are reproducible measurement tools; quality leadership still requires
comparable budgets and a multilingual retrieval evaluation corpus. Later additions
and any breaking-contract candidates belong in the roadmap.
