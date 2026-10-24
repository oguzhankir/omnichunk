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
| `run_retrieval.py` | Source-labeled retrieval evaluation and fixed-budget tuning using a frozen offline lexical baseline. |
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

## Retrieval quality

Run the [retrieval benchmark](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/README.md#retrieval-evaluation-and-tuning)
against the versioned corpus or an identically structured corpus of your own.
The bundled first corpus has 300 synthetic evidence-labeled queries over 30
original MIT-licensed code, Markdown and table documents in English, Turkish and
Japanese. Development and test documents are disjoint. Tune using the development
split, freeze the configuration, then evaluate the test split. Record each corpus
revision; exposing a test set does not protect it from repeated manual tuning.

The baseline uses deterministic character-ngram TF-IDF lexical retrieval, with IDF
fitted on source documents rather than each candidate's chunks. It does not
measure a dense embedding model or generated answers. The labels are authored
and have not had independent human validation. Use the results to investigate
chunking failures and the evaluation process; external corpora, frozen model
revisions and independently reviewed questions remain necessary for a broad
quality claim.

Ranking metrics answer different questions from source-evidence metrics:

The dependency-free public API also scores rankings from your own retriever:

```python
from omnichunk import EvidenceSpan, score_evidence, score_ranking

ranking = score_ranking(["chunk-b", "chunk-a"], {"chunk-a": 1.0}, k=5)
evidence = score_evidence(
    [EvidenceSpan("policy@revision-1", 0, 120)],
    [EvidenceSpan("policy@revision-1", 30, 90)],
)
assert ranking.mrr_at_k == 0.5
assert evidence.recall == 1.0 and evidence.precision == 0.5
```

Coordinates must address the same canonical source revision. `EvidenceSpan`
validates coordinates; the corpus loader additionally validates the actual UTF-8
source slices. Empty positive ranking judgments score zero. Evidence scores are
one when both sets are empty and zero when only one set is empty.

| Metric | Interpretation |
| --- | --- |
| Recall@k | Fraction of relevant candidate passages present in the first k ranks. |
| MRR@k | Reciprocal rank of the first relevant passage, or zero if none is retrieved. |
| nDCG@k | Discounted relevance relative to the ideal ordering of the candidate's relevance labels. |
| Evidence precision | Relevant source bytes divided by retrieved source bytes. |
| Evidence recall | Retrieved relevant source bytes divided by all labeled relevant source bytes. |
| Evidence IoU | Retrieved relevant source bytes divided by the union of retrieved and relevant bytes. |

Chunk boundaries change the candidate passages and their relevance labels. A
candidate can therefore change its ranking scores by changing that item set;
inspect evidence scores and actual retrieved budgets alongside the ranking
metrics. Evidence metrics merge overlapping half-open UTF-8 intervals within each
source and keep different documents separate. Repeated bytes cannot improve the
score. Report empty/missing evidence cases explicitly rather than dropping them.

The benchmark evaluates both the first k results and context selected under a
fixed retrieval capacity. Character and token budgets are separate experiments;
use the same explicit tokenizer for every candidate in a token experiment. Count
actual emitted text, with zero overlap and no derived context for this baseline.
The selected context is a rank prefix joined with two newline separators; its
complete rendered size must fit, and selection stops at the first non-fitting
passage.
All source spans and per-passage capacities must validate before scoring. Missing
competitors are `unavailable`, failed candidates retain diagnostics, and partial
results do not become successful aggregates.

Preserve per-query rankings, language/category slices, corpus and configuration
fingerprints, dependency/runtime versions, raw repeated timings, index size and
memory diagnostics. Python allocation peaks exclude native allocations. Process
peak RSS is a cumulative high-water mark and does not isolate the current
candidate. Report comparable repeated measurements before interpreting small
differences. No single synthetic corpus or configuration establishes leadership.

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
