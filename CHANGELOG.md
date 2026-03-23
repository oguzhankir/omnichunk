# Changelog

All notable changes to omnichunk will be documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- Minhash dedup: faster signatures (one MD5 per token, deterministic mixing for LSH bands); 32 permutations in 8×4 bands; Jaccard verification on candidates unchanged
- Benchmark docs (`benchmarks/README.md`): note interpreting simhash vs minhash on the default `run_v09_stress.py` corpus

## [0.10.1] - 2026-03-23

`v0.10.1` is a stability-focused pre-release before `v1.0.0`, where the formal stable public API guarantee begins.

### Added
- **Documentation site (MkDocs Material)**: `docs/` + `mkdocs.yml`; API stability policy, installation, migration notes (v0.8–v0.10), performance methodology; optional extra `omnichunk[docs]`
- **PEP 561 marker**: `py.typed` shipped in the wheel for type checkers
- **Proposition extraction**: `Chunker.extract_propositions(filepath, text, mode="heuristic"|"llm")` with `Proposition` (`text`, `byte_range`, `confidence`, `metadata`); heuristic mode uses sentence split + regex patterns; LLM mode accepts `llm_fn(filepath, text) -> JSON` with verbatim `claims[].text` matched into the source string
- **Meta-extra `omnichunk[all]`**: bundles most optional integrations (formats, tiktoken, otel, langchain, llamaindex, profiling, all-languages); excludes heavy stacks such as `transformers` and `rust` tooling unless installed explicitly

### Changed
- **Project URLs**: `Documentation` now points at the published docs site (`https://oguzhankir.github.io/omnichunk/`)
- **CI**: builds docs with `mkdocs build --strict` and runs `mypy --strict --follow-imports=skip` on `omnichunk.propositions.*`
- **Versioning policy clarification**: while still in `0.x`, compatibility remains best-effort for documented public APIs; strict stability guarantees start at `v1.0.0`

## [0.10.0] - 2026-03-23

### Added
- **Persistent chunk cache**: `omnichunk.store.ChunkStore` (SQLite, stdlib only) with `index()`, `sync()`, `query()`; incremental updates use mtime, size, and SHA-256; `SyncResult` reports per-file `ChunkDiff`-style removals for vector DB deletes
- **Streaming vector export**: `Chunker.stream_upsert()` yields `UpsertBatch` (Pinecone / Weaviate / Supabase row dicts) with O(batch_size) memory; `UpsertBatch` in `omnichunk.types`
- **MCP-style HTTP server**: `omnichunk serve --mcp --port 3333` — JSON-RPC 2.0 POST over stdlib `http.server`; tools: `chunk_file`, `chunk_directory`, `build_graph`, `semantic_chunk` (with `embed_backend=mock` for deterministic embeddings); optional `--config` JSON for default `Chunker` options; extra `omnichunk[mcp]` reserved for future SDK bridges
- **OpenTelemetry hooks**: `ChunkOptions.otel_tracer` — spans on `chunk_file` (`omnichunk.chunk_file`) with `omnichunk.filepath`, `omnichunk.file_size_bytes`, `omnichunk.chunk_count`, `omnichunk.chunking_duration_ms`, `omnichunk.parse_errors`; directory chunking instruments plain-text files per worker; `omnichunk.otel.maybe_span`; optional extra `omnichunk[otel]` installs `opentelemetry-api`

### Changed
- **`Chunker._build_options`** uses `dataclasses.replace()` instead of `asdict()` so `otel_tracer`, `semantic_embed_fn`, and other callables are not deep-copied

## [0.9.0] - 2026-03-23

### Added
- **Multiformat document loading** (`omnichunk.formats`): canonical UTF-8 text plus `FormatSegment` lists for Jupyter (`.ipynb`, JSON only), LaTeX (`.tex`, sections + `lstlisting` / `verbatim` / `minted` code blocks), PDF (optional `pypdf` via `omnichunk[pdf]`), and Word (optional `python-docx` via `omnichunk[docx]`); combined extra `omnichunk[formats]` installs both parsers
- **`chunk_loaded_document()`** routes each segment to `ProseEngine` or `CodeEngine` with HybridEngine-style byte/line rebasing; `Chunker.chunk_file()` / `chunk_directory()` auto-select loaders by extension; `Chunker.chunk()` accepts `.ipynb` / `.tex` strings (`.pdf` / `.docx` require `chunk_file()` because they are binary on disk)
- **`ChunkContext.format_metadata`** for source hints (cell index, LaTeX env, PDF page, etc.); `Language` extended with `latex`, `jupyter`, `pdf`, `docx`; `.ipynb` maps to `ContentType.HYBRID` in `detect_content_type()`
- **Chunk deduplication**: `dedup_chunks()` with `exact` (SHA-256), `simhash` (64-bit + banded candidate buckets), and `minhash` (token Jaccard + LSH-style bands); returns `(unique_chunks, duplicate_map)` keyed by `Chunk.index`
- **Offline evaluation**: `evaluate_chunks()`, `EvalReport`, `ChunkEvalScores`, `eval_report_to_dict()` — metrics include reconstruction (byte slice vs source), density (NWS vs character count), coherence (intra-chunk TF-IDF sentence similarity), boundary_quality (cross-chunk boundary), coverage (tokens vs source when provided)
- **`chunk_from_dict()`** to rebuild minimal `Chunk` instances from `chunk_to_dict()` JSON (for JSONL workflows)
- **CLI**: `omnichunk eval <chunks.jsonl> [--metrics all|...] [--source <file>] [--output <file>]` for evaluation reports; default `omnichunk <path>` unchanged; `chunk_file` honors `--encoding` in the programmatic API

### Changed
- `chunk_file()` module helper and `Chunker.chunk_file()` accept an explicit `encoding` argument (default `utf-8`); directory chunking uses structured loaders for `.ipynb`, `.tex`, `.pdf`, `.docx` without reading them as plain UTF-8 text first

## [0.8.0] - 2026-03-21

### Added
- Hierarchical / multi-granularity chunking: `Chunker.hierarchical_chunk()`, `ChunkTree`, and `ChunkNode` for leaf→parent retrieval workflows (small chunks for indexing, larger chunks for LLM context windows)
- Incremental / differential chunking: `Chunker.chunk_diff()` and `ChunkDiff` for add/remove/unchanged detection across file revisions using stable IDs
- Token budget optimizer: `TokenBudgetOptimizer` and `BudgetResult` with greedy (`O(N log N)`) and DP knapsack (`O(N * budget)`) selection strategies
- Public `stable_chunk_id()` helper for deterministic vector/document IDs aligned with the existing vector export adapters
- New packages: `omnichunk.hierarchy`, `omnichunk.diff`, and `omnichunk.budget`

### Changed
- `Chunker` now includes top-level convenience methods for hierarchical chunking and incremental diff workflows
- Added module-level convenience function `chunk_diff(...)` alongside `chunk(...)`, `chunk_file(...)`, and `hierarchical_chunk(...)`
- Distribution now includes `examples/` in source builds (`sdist`) and ships runnable v0.8 feature examples

### Fixed
- Python 3.8 compatibility in semantic splitter boundary grouping (removed use of `zip(..., strict=True)`)
- Example scripts now prefer local `src/` imports when run from a repository checkout, avoiding stale site-packages collisions in virtual environments

## [0.7.0] - 2026-03-20

### Added
- Semantic chunking engine: sliding-window cosine similarity boundary detection (`omnichunk.semantic.SemanticSplitter`, `detect_semantic_boundaries`)
- Topic shift detection: TF-IDF based, numpy-only, no external model required (`omnichunk.semantic.detect_topic_shifts`)
- GraphRAG: entity→chunk relationship map with cross-chunk entity links (`build_chunk_graph`, `ChunkGraph`, `EntityNode`, `ChunkEdge`)
- Rust-accelerated adjacent cosine similarity (`batch_cosine_similarity_adjacent`) — falls back to numpy when Rust is not built
- `Chunker.semantic_chunk()` convenience method
- `ChunkOptions` extended with `semantic`, `semantic_embed_fn`, `semantic_window`, `semantic_threshold`, `semantic_min_sentences`, `semantic_sentence_splitter` fields

## [0.6.0] - 2026-03-22

### Added
- Vector DB export adapters: `to_pinecone_vectors()`, `to_weaviate_objects()`, `to_supabase_rows()` (pure dict producers, no client library required)
- Serialization helpers: `chunks_to_pinecone_vectors`, `chunks_to_weaviate_objects`, `chunks_to_supabase_rows`
- Plugin API: `register_parser()`, `register_formatter()`, `list_registered_parsers()`, `list_registered_formatters()` in `omnichunk.plugins`
- HTML benchmark dashboard: `benchmarks/run_html_report.py` and optional `--html-report` on `scripts/check_benchmarks.py`
- Extended language test coverage: C, C++, C#, Ruby, PHP, Kotlin fixtures and entity/reconstruction tests (requires `all-languages` extra / dev grammars)

### Changed
- C/C++ tree-sitter query patterns extended (`struct_specifier`, `type_definition`, `namespace_definition` for C++)
- `parse_code()` accepts optional `filepath` for plugin parsers; `CodeEngine` passes filepath through

### Fixed
- `tree-sitter-swift` optional dependency uses `>=0.0.1` (PyPI has no `0.23.x` wheel); `pip install omnichunk[dev]` and `omnichunk[all-languages]` resolve again on CI

## [0.5.0] - 2026-03-21

### Added
- Async API: `Chunker.achunk()`, `Chunker.astream()`, `Chunker.abatch()`
- Statement-safe oversized splitting: code chunks no longer split mid-expression
- True lazy streaming: `Chunker.stream()` and all engine `stream()` methods are now genuine generators

### Fixed
- Redundant `TextIndex` and NWS cumsum builds in engine delegation paths
- `Chunker.stream()` now documents that overlap is not applied in streaming mode

### Performance
- `TextIndex.__init__` Rust acceleration via `build_char_to_byte_index` (5× speedup)
- `_compile_query` result cached per language (eliminates redundant tree-sitter query compilation)
- `_find_query_name_capture` O(N) → O(log N) via bisect index

## [0.4.0] - 2026-03-20

### Changed
- Reuse precomputed `TextIndex` and NWS cumulative sums in HybridEngine to avoid repeated per-segment recomputation
- Reuse precomputed indices for delegated markdown fence code blocks in ProseEngine to reduce redundant engine setup
- Added regression tests to verify precomputed index reuse in hybrid and prose markdown delegation paths

## [0.3.0] - 2026-03-19

### Added
- Added first-class CLI (`omnichunk`) with file/directory chunking, JSON/JSONL/CSV outputs, and `--stats` reporting
- Added `chunk_directory()` API for recursive repository chunking with glob/exclude/concurrency options
- Added export helpers on `Chunker`: `to_dicts()`, `to_jsonl()`, `to_csv()`, `to_langchain_docs()`, `to_llamaindex_docs()`
- Added chunk quality metrics and aggregate stats APIs via `quality_scores()` and `chunk_stats()`
- Added test coverage for CLI flow, directory chunking, export serialization, and quality scoring

### Changed
- Router now precomputes and reuses `TextIndex` and NWS cumulative sums across engines to reduce repeated full-content scans
- Tree-sitter parser instances now use per-thread caching to avoid cross-thread parser reuse in concurrent workloads

## [0.2.0] - 2026-03-19

### Fixed
- Improved tree-sitter entity extraction by adding `@name` captures to language query patterns and mapping captured name nodes before regex fallback
- Reworked code doc extraction to use AST-positioned logic (Python first-statement docstring, adjacent leading comments for JS/TS and C-like languages)
- Added language-specific import parsing for Rust (`use ...::{...}` groups), Go (`import (...)` blocks), and Java (static/non-static imports)
- Recomputed merged chunk context during token-overlap post-processing so entities/imports/siblings are preserved across grouped chunks
- Recomputed `is_partial` entity flags against merged overlap ranges instead of reusing the first chunk context
- Removed dead computation in prose `_windows_to_contiguous_ranges` and now respect each window's actual start offset

## [0.1.2] - 2026-03-19

### Fixed
- Fixed Python 3.10/3.11 compatibility by ignoring B905 ruff rule for zip() calls
- Updated badge cache-buster to v=2 for proper GitHub rendering
- Fixed CI failures across all Python versions (3.10-3.13)

## [0.1.1] - 2026-03-19

### Fixed
- Fixed README logo URL path from `assets/logo/` to `assets/`
- Added cache-buster parameters to badge URLs for proper GitHub rendering
- Improved README layout with centered logo and badges

## [0.1.0] - 2026-03-19

### Added

- Code engine with tree-sitter AST parsing for Python, JavaScript, TypeScript, Rust, Go, Java
- Extended language support (C, C++, C#, Ruby, PHP, Kotlin, Swift) via optional grammars
- Prose engine with Markdown heading hierarchy, section tree, and semantic splitter fallback
- Markdown fenced code block delegation to CodeEngine (Python, JS, TS, etc.) and MarkupEngine (JSON, YAML, etc.)
- Markup engine for JSON, YAML, TOML, HTML, XML structural chunking
- Hybrid engine for notebook-style `# %%` cell files and docstring-heavy Python
- Rich chunk context: scope chain, entity signatures, siblings, import tracking, breadcrumbs
- Heading hierarchy tracking for prose and Markdown content
- `contextualized_text` output optimized for embedding models
- Token-aware sizing with tiktoken and transformers tokenizer support
- Character and non-whitespace sizing modes
- NWS cumulative sum preprocessing for O(1) range queries
- Memoized token counter with long-text short-circuit optimization
- Greedy AST window assignment with adjacent window merging
- Oversized node splitting at line and safe-character boundaries
- Line-based overlap for `contextualized_text`
- Token-based overlap with semchunk-style chunk resequencing
- Streaming API (`chunker.stream()`) for incremental chunk generation
- Batch processing API (`chunker.batch()`) with concurrent execution
- File API (`chunk_file()`) for direct disk reads
- Deterministic output guarantee (same input + options = identical output)
- Byte-range integrity guarantee (`source[start:end] == chunk.text`)
- Contiguous non-overlapping chunk ranges
- Graceful degradation for malformed syntax and missing parsers
- Tree-sitter query patterns for entity extraction across all supported languages
- Regex fallback entity extraction when tree-sitter is unavailable
- Benchmark suite with comparison runners against LangChain and semantic-text-splitter
- Quality report runner verifying reconstruction, contiguity, determinism
- Gutenberg corpus benchmark for large-scale throughput testing
- CI pipeline with Python 3.10-3.12, pytest, ruff, mypy
- AI rules synchronization across `.cursorrules`, `.windsurfrules`, `CLAUDE.md`, copilot-instructions
- Pre-commit hooks for ruff, mypy, pytest, rule sync

[0.9.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.9.0
[0.8.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.8.0
[0.7.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.7.0
[0.6.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.6.0
[0.5.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.5.0
[0.4.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.4.0
[0.3.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.3.0
[0.2.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.2.0
[0.1.2]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.1.2
[0.1.1]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.1.1
[0.1.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.1.0
