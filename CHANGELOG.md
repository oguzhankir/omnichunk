# Changelog

All notable changes to omnichunk will be documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

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

[0.1.0]: https://github.com/oguzhankir/omnichunk/releases/tag/v0.1.0
