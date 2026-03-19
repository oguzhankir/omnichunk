# Profiling Report — Pre-Rust Migration

Date: 2026-03-20  
Corpus: **mega-python** (repeat=120, `max-size=512`, `size-unit=chars`), **fixtures** (repeat=500), **directory** on this repo’s `src/` (38 `.py` files, `max-files=500`)  
Machine: Apple M3 Pro, 18 GB RAM, macOS 26.3.1, Python 3.12.0 (project `.venv`)

**Environment note:** `nws_backend=auto` selected the **Python** NWS path (`omnichunk_rust` not installed: `ModuleNotFoundError`). Hotspot numbers below are **Python NWS + Python core** only.

**CPython stdlib:** No local `Lib` tree was available under common paths; **Part 1b** used `directory` mode on `/Users/oguz/Desktop/omnichunk/src` instead of CPython’s `Lib`.

## Throughput summaries (from `run_large_corpus.py`)

| Run | Files | Bytes (approx) | Chunks | Seconds | MB/s |
|-----|------:|---------------:|-------:|--------:|-----:|
| mega-python r=120, max 512 chars | 1 | 360,883 | 720 | 1.95 | ~0.18 |
| fixtures r=500 | 4,500 | 3,350,000 | 15,500 | 6.88 | ~0.46 |
| directory `src/**/*.py` | 38 | 197,225 | 391 | 0.17 | ~1.14 |

Raw JSON: `results/large_corpus_mega_python.json`, `results/large_corpus_fixtures.json`, `results/large_corpus_src_tree.json`.

## Summary (exclusive CPU — mega-python, repeat=120, sorted by `tottime`)

Profile wall ~**4.83 s** for one pass over the synthetic file (`results/hotspot_mega_python_tottime.txt`, cProfile total ~4.81 s). Percent of cProfile total shown for orientation.

| Rank | Function | Module | tottime (s) | % of cProfile total | Rust candidate? |
|------|----------|--------|-------------|---------------------|-----------------|
| 1 | `_find_query_name_capture` | `context/entities.py` | 2.83 | ~59% | NO — tree-sitter/query orchestration |
| 2 | `getattr` (builtin) | — | 1.24 | ~26% | NO — Python / attribute access |
| 3 | `_entities_in_range` | `engine/code_engine.py` | 0.12 | ~2.6% | LOW — glue over entity model |
| 4 | `_find_deepest_container` | `context/scope.py` | 0.11 | ~2.2% | MAYBE — hot loop, but logic-heavy |
| 5 | `build_scope_tree` | `context/scope.py` | 0.08 | ~1.7% | MAYBE — one-shot per file |
| 6 | `__init__` | `util/text_index.py` | 0.07 | ~1.5% | YES — pure UTF-8 width / index (post v0.5.0) |
| 7 | `_contains` | `context/scope.py` | 0.07 | ~1.5% | MAYBE |
| 8 | `find_scope_chain` | `context/scope.py` | 0.05 | ~1.0% | MAYBE |
| 9 | `greedy_assign_windows` | `windowing/greedy.py` | 0.004 | &lt;0.1% | CANDIDATE — only if profiles on other corpora rise |
| — | `_hard_split` | `windowing/split.py` | (not in top 35) | — | Not hot on this corpus/settings |

`preprocess_nws_cumsum_python` / `preprocess_nws_cumsum` were **&lt;0.01 s** exclusive in this mega-python run (single-file cumsum; Rust backend not active here). Mark **DONE (v0.4.0)** for environments where the Rust extension is installed.

**Deep filtered table** (`benchmarks/run_profiler_deep.py`, repeat=60, filter on engine/context/windowing/sizing/text_index): see `results/deep_profile.txt` and `results/deep_profile.json`.

## Findings

### `TextIndex.__init__`

One call builds `char_to_byte` over the full document. Before optimization, **`ch.encode("utf-8")` per code point** allocated a bytes object every iteration. The profile still shows this as a visible exclusive cost (~0.07 s on the mega file, **~1.5%** of total cProfile time) alongside **~361k `ord()`** calls (some from this loop, some from other hot paths).

**Change shipped in this task:** UTF-8 width via `ord(ch)` and branch on code-point range (same mapping as UTF-8 for scalar values), preserving `char_to_byte` / `line_starts` vs a per-character `encode` reference (`tests/test_text_index.py`).

### `preprocess_nws_cumsum`

With **Rust NWS unavailable**, Python preprocessing still did not register as a top exclusive cost on mega-python (work amortized per file). When `omnichunk_rust` is present, expect the published **v0.4.0** Rust path to dominate; re-profile after enabling the extension.

### `windowing/split._hard_split`

**Not in the top 35** by `tottime` for mega-python at `max-size=512` chars. Greedy windowing shows small exclusive time (`greedy_assign_windows` ~0.004 s). Treat **`_hard_split` as corpus-dependent**; revisit if directory or larger-chunk settings shift the profile.

### `extract_entities` / query path

**`extract_entities`** has low exclusive time but **high cumulative** time: the dominant exclusive work sits in **`_find_query_name_capture`** and **`getattr`** inside tight loops over tree-sitter nodes. This is **algorithm and API churn**, not a single arithmetic kernel — a poor first Rust target compared to **`TextIndex`** byte-index construction.

## Decision: What Goes to Rust in v0.5.0

### Completed (v0.4.x)

- `preprocess_nws_cumsum_bytes` — DONE v0.4.0
- `build_char_to_byte_index` — DONE v0.4.x

### No further Rust candidates identified

Current top hotspots (0.064s and below) are:
- Tree-sitter query execution — external C library, not portable to Rust
- `format_contextualized_text` — string templating, not arithmetic
- `greedy_assign_windows` — already O(N), not a bottleneck

Python optimization complete. Next phase: v0.5.0 async API.

## Artifact index

| Artifact | Description |
|----------|-------------|
| `results/hotspot_mega_python.txt` | cProfile mega-python r=120, default chunk args (historical) |
| `results/hotspot_mega_python_tottime.txt` | Same corpus, `max-size=512`, `--sort tottime` |
| `results/hotspot_src_tree.txt` | Directory mode on `src/` |
| `results/deep_profile.txt` / `deep_profile.json` | Structured deep profile (`run_profiler_deep.py`) |
| `results/deep_profile_post_fix.json` | Post entity-fix profile |
| `results/deep_profile_rust_enabled.json` | Rust NWS active, pre TextIndex port |
| `results/deep_profile_rust_text_index.json` | Rust NWS + TextIndex active (final) |

## Optimization Timeline (Final)

### Phase 1 — Algorithm fix: `_find_query_name_capture` bisect index

- Before: fixtures r=200 total ~3.86s, `_find_query_name_capture` 2.83s tottime (~59%)
- After: `_find_query_name_capture` dropped out of top 15, tottime ~0.021s
- Method: replaced O(entity × name × depth) linear scan with `bisect_left` index + early break

### Phase 2 — Cache fix: `_compile_query` `lru_cache`

- Before: 1000 calls × ~1.8ms = 1.819s tottime (~47% of 3.86s)
- After: 3 cache misses total, tottime 0.007s
- Method: `@lru_cache(maxsize=32)` on `_compile_query_cached`

### Phase 3 — Rust port: `TextIndex.build_char_to_byte_index`

- Before: 0.318s tottime, 3000 calls, ~15.9% of total
- After: 0.064s tottime, 5× speedup
- Method: `build_char_to_byte_index(data: &[u8]) -> (Vec<u32>, Vec<u32>)` in `lib.rs`, GIL released

### Final state (fixtures r=200, Rust active)

- Total seconds: 1.57s (baseline was ~3.86s, overall ~2.5× improvement)
- Top hotspot: `TextIndex.__init__` 0.064s / 4.1%
- Profile is flat — no single function dominates
- `nws_backend_active: true`
