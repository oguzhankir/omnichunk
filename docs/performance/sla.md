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

## TF-IDF memory (sparse vs dense)

Topic-shift detection builds a sentence-level TF-IDF matrix. The dense
representation (`build_tfidf_matrix`) allocates `N × V` float64 cells, which is
mostly zeros for real documents (each sentence touches a small slice of the
vocabulary). `build_tfidf_sparse` (requires `pip install omnichunk[scipy]`)
stores only nonzero entries as a `scipy.sparse.csr_matrix`.

For a synthetic **2000-sentence** document over a 2048-term vocabulary
(~10 terms per sentence), the sparse CSR footprint is **>50% smaller** than the
dense array; the gap widens as documents grow. The dense API is unchanged and
remains the default; switch to the sparse builder for large-corpus pipelines.
Measure on your own data with `python benchmarks/bench_tfidf_memory.py`.

## CI policy

Continuous integration runs a **quality regression gate** (`scripts/check_benchmarks.py`); full throughput comparisons are **not** required on every PR by default.
