# Omnichunk

**Omnichunk** splits source files and documents into structure-aware chunks for
RAG, embeddings, and LLM context windows.

## Features

- Code, prose, and markup routing with tree-sitter where available
- Chunk text with byte/line ranges, entities, scopes, imports and heading context
- Notebook, LaTeX and RST loaders; PDF/DOCX text extraction with optional extras
- Semantic boundaries, embedding caching, topic shifts and MMR reranking
- Hierarchical chunks, chunk diffs, deduplication, entity graphs and token budgets
- Vector export helpers (Pinecone / Weaviate / Supabase shapes) without vendor SDKs
- `ChunkStore` for SQLite-backed incremental indexing
- `omnichunk serve --rpc` for constrained custom HTTP JSON-RPC tools

Offsets refer to the declared canonical text, including extracted text for
document loaders. They do not reconstruct original binary documents or notebook
JSON. Public chunking paths share measured payload limits, explicit lossless or
retrieval coverage, versioned metadata and configuration-aware identity. Source
and AST state remain in memory even when chunk output is streamed. See the
[contract reference](reference/contracts.md) and [API policy](api-stability.md).

## Development direction

The [2.0–4.0 roadmap](https://github.com/oguzhankir/omnichunk/blob/main/ROADMAP.md)
records the original audit, implemented 2.0 foundations and 2.1 code-quality
changes, subsequent compatible features, and longer-term research. The combined
changes target the next **2.1.0** release; publication and the maintainer's version
bump are separate. See the [migration guide](migrations/v2.md).

## Quick links

- [Installation](install.md)
- [API stability policy](api-stability.md)
- [Upgrade notes](migrations/index.md)
- [Performance methodology](performance/sla.md)

## Project

- [Source on GitHub](https://github.com/oguzhankir/omnichunk)
- [Changelog](https://github.com/oguzhankir/omnichunk/blob/main/CHANGELOG.md)
