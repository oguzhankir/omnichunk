# Architecture

## High-level flow

1. Detect language/content type (`util/detect.py`)
2. Route to engine (`engine/router.py` / `route_content_stream`)
3. Parse/extract structure (AST or structural parser)
4. Build chunk windows (`windowing/*`)
5. Attach context (`context/*`)
6. Build final chunks (`types.Chunk`)

Streaming uses the same routing and engine logic but yields chunks incrementally with `total_chunks=-1`.

## Engines

- `CodeEngine`: tree-sitter + entity/scope context
- `ProseEngine`: heading/section-aware chunking, fenced block delegation
- `MarkupEngine`: key/element-aware chunking
- `HybridEngine`: mixed code/prose segmentation

Markdown fenced blocks are delegated by fence language:

- code fences (for example `python`, `typescript`) -> `CodeEngine`
- markup fences (for example `json`, `yaml`, `toml`, `html`, `xml`) -> `MarkupEngine`

Delegated chunks are rebased to original markdown byte ranges.

## Parsing and extraction

- `parser/tree_sitter.py` provides parse trees for supported code languages.
- `context/entities.py` uses query-driven extraction when query patterns are available (`parser/query_patterns.py`), then falls back to iterative AST traversal.
- Regex fallback is used when parser support is unavailable.

## Benchmark and quality tooling

- `benchmarks/run_benchmarks.py`: throughput/latency across fixed scenarios
- `benchmarks/run_comparisons.py`: optional comparison runner for installed competitor tools
- `benchmarks/run_quality_report.py`: reconstruction/contiguity/non-empty/determinism checks on benchmark scenarios

## Invariants

- Byte ranges reconstruct source slices
- Chunk ranges are contiguous and non-overlapping
- No whitespace-only chunks
- Deterministic results for same input/options
