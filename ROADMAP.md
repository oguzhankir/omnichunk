# Roadmap

## Completed (v0.5.x–0.6.x)

- Statement-safe oversized splitting for code
- Real streaming API (`Chunker.stream`, async `achunk` / `astream` / `abatch`)
- Shared `TextIndex` / NWS reuse in hybrid and delegation paths
- Vector DB export adapters (Pinecone / Weaviate / Supabase-shaped dicts, no client deps)
- Plugin registry for custom parsers and formatters
- HTML benchmark dashboard + CI hook (`--html-report`)
- Extended language fixtures and tests (C, C++, C#, Ruby, PHP, Kotlin)

## Near term (P0) — v0.7.0 target

- Formatter plugins wired into CLI / export paths where appropriate
- Scope-level sibling accuracy improvements
- Better import usage filtering from AST symbol usage
- Benchmark baselines and richer regression metadata

## Mid term (P1)

- Language-specific tree-sitter query packs (ongoing refinement)
- Markdown fenced-code routing improvements
- Benchmark suite against additional baseline chunkers

## Longer term (P2)

- Performance dashboard iterations (historical trends)
- Extended Swift coverage when grammar install story is stable across platforms
- Mixed-format and notebook coverage expansion
