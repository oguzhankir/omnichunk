# Benchmarks

This folder contains reproducible benchmark scripts for `omnichunk`.

## Goals

- Track latency and throughput across representative workloads
- Catch performance regressions over time
- Compare configuration changes with stable scenarios

## Run

```bash
python benchmarks/run_benchmarks.py
```

Run optional tool comparisons (if competitor packages are installed):

```bash
python benchmarks/run_comparisons.py
python benchmarks/run_comparisons.py --corpus mega-fixture --no-table
python benchmarks/run_comparisons.py --corpus mega-python --repeat 50
python benchmarks/run_comparisons.py --corpus smoke
python benchmarks/run_comparisons.py --include-extra   # adds astchunk
```

**Interpreting `run_comparisons.py`:** The default `--corpus all` includes both **tiny** fixtures (~5 KB total) and **`mega_python_50x`** (~150 KB synthetic Python). On tiny inputs, generic splitters finish in tens of microseconds (often dominated by interpreter overhead); **omnichunk** still pays tree-sitter parse, entity extraction, and scope work every call — so **sub-1× “speedup” lines on smoke-sized data are expected, not a bug**. For apples-to-apples throughput, prefer **`--corpus mega-fixture`** or **`--corpus mega-python`**, or run prose at scale with Gutenberg (below).

**Prose / multi-MB comparison (realistic throughput):**

```bash
python benchmarks/run_gutenberg.py
```

Requires NLTK data (`nltk.download("gutenberg")`) and optional competitor deps plus `tiktoken` where used.

Example output (from this machine; 18 Gutenberg texts, ~11.79M chars):

| Tool | Chunks | Avg tokens/chunk | Seconds | MB/s |
|---|---:|---:|---:|---:|
| omnichunk | 4,562 | 657.883 | 4.930 | 2.281 |
| langchain_recursive | 6,689 | 448.686 | 5.187 | 2.168 |
| semantic_text_splitter | 29,807 | 100.690 | 3.548 | 3.170 |
| semchunk | 7,390 | 406.124 | 7.596 | 1.481 |

Run quality invariants report on benchmark scenarios:

```bash
python benchmarks/run_quality_report.py
```

Run large-corpus throughput and slow-file diagnostics:

```bash
python benchmarks/run_large_corpus.py --mode mega-python --repeat 120
python benchmarks/run_large_corpus.py --mode directory --directory ./src --glob "**/*.py"
```

Run cProfile hotspot analysis:

```bash
python benchmarks/run_hotspot_profile.py --mode mega-python --repeat 120 --limit 30
python benchmarks/run_hotspot_profile.py --mode directory --directory ./src --glob "**/*.py" --limit 40
```

## Regenerate `mega_python_50x.py`

The file `tests/fixtures/mega_python_50x.py` is `python_complex.py` repeated 50× (same source as `workloads.mega-python`). Regenerate after changing the base fixture:

```bash
.venv/bin/python -c "
import sys
from pathlib import Path
ROOT = Path('.').resolve()
sys.path.insert(0, str(ROOT / 'benchmarks'))
from workloads import collect_corpus_entries
e = collect_corpus_entries(
    mode='mega-python', repeat=50, directory=None, glob_pattern='**/*', max_files=500,
)
(ROOT / 'tests/fixtures/mega_python_50x.py').write_text(e[0].text, encoding='utf-8')
"
```

## Notes

- Benchmarks are deterministic for the same inputs/options.
- The script prints per-scenario timings and aggregate throughput.
- Add new scenarios by extending the `SCENARIOS` list in `run_benchmarks.py`.
- Default comparison includes `omnichunk`, `langchain_recursive`, `semantic_text_splitter`, and `semchunk`.
- **`--corpus`:** `all` (default) = every `SCENARIOS` row; `smoke` = small fixtures only (excludes `mega_python_50x`); `mega-fixture` = only on-disk mega file; `mega-python` = synthetic mega from `workloads` + temp file, use `--repeat`.
- `--include-extra` adds `astchunk` / `astchunker` attempts.
- Comparison runner marks tools as `unavailable` when dependencies are missing or import fails.
- Each tool×scenario run does one **untimed warmup** call before `perf_counter`, so heavy first-import / init (notably LangChain) is not charged only to the first scenario in the CSV.
- **Speedup lines** use `competitor_total_seconds / omnichunk_total_seconds`: above **1×** means omnichunk was faster on aggregate for this run; below **1×** means a competitor was faster (tiny fixtures often favor trivial splitters).
- `run_comparisons.py` exits via `os._exit` after a stream flush so Python 3.12 does not print a spurious `multiprocess.resource_tracker` traceback when **semchunk** has been loaded (upstream `ResourceTracker.__del__` bug).
- Quality report verifies reconstruction, contiguity, non-empty chunks, and determinism.
- `run_large_corpus.py` supports `--nws-backend auto|python|rust` for backend experiments.
- `run_hotspot_profile.py` highlights likely bottlenecks in `sizing`, `windowing`, and `context` modules.
