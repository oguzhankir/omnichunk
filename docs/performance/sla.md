# Performance methodology

Omnichunk does **not** publish a fixed throughput SLA (MB/s or chunks/s) for all hardware and corpora. Instead, this page documents **how to reproduce** performance numbers and what they mean.

## Benchmarks layout

Scripts live under [`benchmarks/`](https://github.com/oguzhankir/omnichunk/tree/main/benchmarks). See the benchmark README for:

- `run_benchmarks.py` — core latency/throughput scenarios
- `run_comparisons.py` — optional comparisons with other tools
- `run_gutenberg.py` — large prose throughput
- `run_quality_report.py` — quality invariants

## Reference environment

When you run benchmarks, record:

- **Omnichunk version** (`python -c "import omnichunk; print(omnichunk.__version__)"`)
- **Git commit** (`git rev-parse HEAD`)
- **Python version**
- **CPU model** (optional) and whether Rust acceleration is active (`omnichunk_rust`)

## Engines

Throughput differs by engine:

- **Code** paths use tree-sitter parsing and entity extraction (more work per byte than naive splitters).
- **Prose** paths use Markdown/prose heuristics.
- **Semantic** modes call embedding functions (dominated by your embedder).

## Interpreting comparisons

On tiny inputs, tree-sitter and parsing overhead can dominate wall time; **prefer larger corpora** (see benchmark README “Interpreting `run_comparisons.py`”).

## CI policy

Continuous integration runs a **quality regression gate** (`scripts/check_benchmarks.py`); full throughput comparisons are **not** required on every PR by default.
