# Omnichunk

**Omnichunk** splits source files and documents into **deterministic**, **structure-aware** chunks for RAG, embeddings, and LLM context windows.

## Features

- Code, prose, and markup routing with tree-sitter where available
- Lossless byte and line ranges for reconstruction
- Optional multiformat loaders (`.ipynb`, LaTeX, PDF/DOCX with extras)
- Vector export helpers (Pinecone / Weaviate / Supabase shapes) without vendor SDKs
- `ChunkStore` for SQLite-backed incremental indexing
- `omnichunk serve --mcp` for JSON-RPC tool access (stdlib HTTP server)

## Quick links

- [Installation](install.md)
- [API stability policy](api-stability.md)
- [Upgrade notes](migrations/index.md)
- [Performance methodology](performance/sla.md)

## Project

- [Source on GitHub](https://github.com/oguzhankir/omnichunk)
- [Changelog](https://github.com/oguzhankir/omnichunk/blob/main/CHANGELOG.md)
