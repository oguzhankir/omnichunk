# Performance methodology

Omnichunk has no universal throughput SLA. Measure a fixed corpus and configuration
on a recorded environment; timing and chunk counts do not establish retrieval quality.

## Comparable workloads

The [benchmark runners](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/README.md)
serve different purposes:

| Runner | Measurement contract |
| --- | --- |
| `run_benchmarks.py` | Local core scenarios for latency/throughput diagnostics. |
| `run_comparisons.py` | Matching character capacities, zero overlap and no derived context; token scenarios use the same explicit `cl100k_base` counter. Emitted payload sizes are validated. |
| `run_gutenberg.py` | All supported tools use 512 `cl100k_base` tokens and zero overlap; counts come from actual output chunks and throughput uses UTF-8 bytes. |
| `run_quality_report.py` | Structural source/coverage/determinism checks, separate from retrieval evaluation. |
| `check_benchmarks.py --compare-ref REF` | Controlled comparison with a prior source revision using one interpreter, dependency environment and reference harness. |

Comparison adapters never substitute word counts or silently change units.
Unsupported dependencies/APIs are reported as unavailable; the ASTChunk adapter
is excluded until its budget/overlap semantics are verified. An oversized output
fails validation. Partial scenario totals cannot supply timing ratios. The runner
reports descriptive ratios for matching complete runs and does not select a library
winner; its exit code reflects execution/validation errors, not competitive speed.

Gutenberg auditing reports input tokens, total/mean/maximum output chunk tokens and
number of overflowing chunks. Input/output auditing happens outside its splitting
timer. It requires an already installed corpus and tokenizer assets. Historical
Gutenberg results from the mixed character/token harness are not comparable to
these measurements.

## Environment and interpretation

Record source commit, package/Python/dependency versions, CPU/platform, tokenizer
assets, corpus hash/license, size and overlap policies, and optional Rust use.
Keep raw repeated timing samples; larger fixtures reduce timer/import noise.
Code parsing/extraction performs different work from plain splitting. Embedding and
loader extraction costs should be reported separately when diagnosing a pipeline.
Both benchmark throughput labels currently use powers of 1024: MiB/s of UTF-8 data.

The [execution contracts](../reference/contracts.md#overlap-and-iteration) describe
resident source/parser data and queue bounds. Measure peak RSS as well as elapsed
time when assessing large documents. Dense TF-IDF stores a sentence-by-vocabulary
array; `build_tfidf_sparse` with the `scipy` extra stores nonzero entries. Use
`benchmarks/bench_tfidf_memory.py` to measure the tradeoff on your data.

## Regression and release evidence

Ordinary CI runs quality checks. The historical machine-local throughput command
explicitly skips when its optional `baseline.json` is absent; it is not a release
speed guarantee. A release requires the separate prior-revision comparison.

The reference gate measures repeated chunks with the same 512-character budget,
no rendered context, zero overlap and Python NWS backend. It records source/corpus
hashes, dependencies, raw timing samples, actual maximum payload size and complete
reconstruction. Invalid output, dependency mismatch or missing required baseline
fails validation; a valid comparable baseline applies a 10% regression threshold.

A legacy release that exceeded the requested budget cannot establish speed parity
for the new contract. The first 2.x transition can instead use an explicit reviewed
transition manifest bound to the old revision, reference settings, corpus/harness
and new behavior source. It establishes the first valid baseline without a speed
parity claim. Later releases compare against a valid 2.x predecessor. Preserve the
comparison JSON with release artifacts; do not promote a laptop timing into a
hardware-independent SLA.

Multilingual retrieval quality, citation accuracy, latency distributions and peak
memory remain distinct evaluation axes in the
[roadmap](https://github.com/oguzhankir/omnichunk/blob/main/ROADMAP.md).
