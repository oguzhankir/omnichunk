# Changelog

All notable changes to omnichunk will be documented here.
This project follows [Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-03-19

### Fixed
- Improved tree-sitter entity extraction by adding `@name` captures to language query patterns and mapping captured name nodes before regex fallback
- Reworked code doc extraction to use AST-positioned logic (Python first-statement docstring, adjacent leading comments for JS/TS and C-like languages)
- Added language-specific import parsing for Rust (`use ...::{...}` groups), Go (`import (...)` blocks), and Java (static/non-static imports)
- Recomputed merged chunk context during token-overlap post-processing so entities/imports/siblings are preserved across grouped chunks
- Recomputed `is_partial` entity flags against merged overlap ranges instead of reusing the first chunk context
- Removed dead computation in prose `_windows_to_contiguous_ranges` and now respect each window's actual start offset

## [0.1.2] - 2025-03-19

### Fixed
- Fixed Python 3.10/3.11 compatibility by ignoring B905 ruff rule for zip() calls
- Updated badge cache-buster to v=2 for proper GitHub rendering
- Fixed CI failures across all Python versions (3.10-3.13)

## [0.1.1] - 2025-03-19

### Fixed
- Fixed README logo URL path from `assets/logo/` to `assets/`
- Added cache-buster parameters to badge URLs for proper GitHub rendering
- Improved README layout with centered logo and badges

## [0.1.0] - 2025-XX-XX

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
