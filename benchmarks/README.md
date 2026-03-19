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
python benchmarks/run_comparisons.py --include-extra
```

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

## Notes

- Benchmarks are deterministic for the same inputs/options.
- The script prints per-scenario timings and aggregate throughput.
- Add new scenarios by extending the `SCENARIOS` list in `run_benchmarks.py`.
- Default comparison includes `omnichunk`, `langchain_recursive`, and `semantic_text_splitter`.
- `--include-extra` adds `semchunk` and `astchunk` attempts.
- Comparison runner marks tools as `unavailable` when dependencies are missing or import fails.
- Quality report verifies reconstruction, contiguity, non-empty chunks, and determinism.
- `run_large_corpus.py` supports `--nws-backend auto|python|rust` for backend experiments.
- `run_hotspot_profile.py` highlights likely bottlenecks in `sizing`, `windowing`, and `context` modules.
