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

### Structural boundary evaluation snapshot

The prose-boundary repair compares baseline `71c5177` with implementation
`58a6b41` on the unchanged `corpus_v1` corpus and lexical retriever. Both use zero
overlap, no derived context, 1,024-character retrieval capacity, top-k 5 and three
timing repeats. The implementation was frozen before evaluating the test split.
These are character-budget experiments, not model-token or dense-retrieval scores.

| Split | Chunk capacity | Evidence recall before → after | Indexed chunks before → after |
| --- | --- | --- | --- |
| Development | 128 chars | 0.8892 → 0.9026 | 312 → 348 |
| Development | 256 chars | 0.9414 → 0.9744 | 162 → 181 |
| Test | 128 chars | 0.8896 → 0.8883 | 206 → 245 |
| Test | 256 chars | 0.9290 → 0.9566 | 115 → 131 |

At 256 characters, test Markdown/table evidence recall reaches 1.0; code stays at
0.8698. Overall evidence precision improves from 0.1313 to 0.1335. At 128
characters, test Markdown recall falls from 0.9856 to 0.9379, while table recall
improves from 0.9285 to 0.9539. Preserving structural units produces more chunks,
which can increase embedding/index cost. Evaluate the relevant slices before
choosing a capacity; smaller chunks are not automatically better.

The strongest evaluated 256-character alternatives still reach 0.9833 overall
test recall. This repair establishes a narrower structural improvement, not
leadership. Independently reviewed labels and external/dense evaluations remain
open. Reproduce with the linked runner commands using `--split dev` and
`--split test`, `--chunk-sizes 128 256 --retrieval-budget 1024 --top-k 5 --repeats 3`.
The CI `retrieval-evaluation` artifact retains raw development results per commit.

## Environment and interpretation

### Independent English prose check

The frozen `corpus_squad_v1` subset adds 32 Wikipedia paragraphs and 96 SQuAD 1.1
human-annotated questions. Eight entire articles belong to each local split.
The upstream SQuAD development file supplies both local splits; this is a chunk
retrieval experiment, not an official SQuAD score. Selection uses hashes rather
than retrieval outcomes. Exact short-answer spans provide independently authored
labels; their suitability as complete supporting evidence still needs review.

With the frozen lexical retriever, zero overlap, no derived context, a
1,024-character retrieved context and top-k 5, test evidence recall is:

| Chunker | 128 characters | 256 characters |
| --- | --- | --- |
| OmniChunk | 0.9192 | 0.9792 |
| Fixed | 0.8907 | 0.9375 |
| semchunk | 0.9167 | 0.9792 |
| LangChain | 0.8963 | 0.9583 |
| semantic-text-splitter | 0.9401 | 0.9792 |
| Chonkie | 0.8854 | 0.9792 |
| LlamaIndex | 0.8963 | 0.9583 |

These 48 held-out questions are a small English prose check. OmniChunk ties
several alternatives at 256 characters and trails semantic-text-splitter at 128.
The synthetic development experiment still has stronger alternatives in some
configurations. Neither result establishes leadership or dense-model quality.
The raw external reports, including per-query ranks, payloads, source/dependency
hashes and timing samples, are preserved in
[`benchmarks/retrieval/reports`](https://github.com/oguzhankir/omnichunk/tree/main/benchmarks/retrieval/reports).
Reproduce with the [benchmark commands](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/README.md).

### Pretrained dense comparison

The historical [v1 dense record](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/retrieval/reports/dense-minilm-v1/README.md)
compares v2.2.0 with source `a2e3bae7afb9b81f7c044ac0feda6612b0f97c97` using
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at model commit
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`. Its original test reports remain
historical evidence; previously observed splits cannot serve as fresh validation
for later source selection.

The [structural-quality v2 record](https://github.com/oguzhankir/omnichunk/blob/main/benchmarks/retrieval/reports/structural-quality-v2/README.md)
fixes candidate `386b5ce99d4508a62725d6b36883dfa999715e8c` against previous
main `511c1cc50db8549060c9ab642ded2da96619e3db`, retaining the v2.2.0 release
baseline separately. Development diagnosis led to paragraph/owning-heading
boundaries, documented code-statement groups including fitting inline comment
chains, semicolon clause fallback and balanced-square-bracket guards for prose
sentence fallback. Full source budgets take precedence over grouping; unmatched
brackets do not hide subsequent boundaries. These rules use no learned model or
query/language identifiers.

The new SQuAD 1.1 corpus excludes all 16 previously observed articles and selects
32 new articles by the recorded protocol: three original paragraphs per article,
three questions per paragraph, and 16 article documents/144 questions in each
split. Text and Markdown views share the questions and differ only in declared
rendering, including a synthetic title heading in Markdown. They are correlated
views, and connected-source bootstrap units are entire articles. Validation
source, questions and answers were encrypted until source/model/configuration
freeze; custody was within the same workspace. Procedural blindness does not
imply unseen model pretraining or independent external custody.

The v2 matrix uses `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
at `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` and English
`sentence-transformers/all-MiniLM-L6-v2` at
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Within each model's experiment,
all six token-compatible adapters use that model's native tokenizer including
special tokens, 64/96-token chunks, zero overlap and no derived context. The
primary complete retrieval prefix fits 512 tokens, with predeclared 128/256-token
sensitivity checks. Top-k 5 separately defines ranking metrics. Encoder input
limits are enforced without truncation; retrieval-context capacity does not mean
that complete context is embedded as a single model input.

Chunking timing has three repeats, with two threads in each PyTorch CPU pool and
OMP/MKL limited to two. Shared deduplicated encoder preparation cannot be assigned
to one chunker. Frozen-vector search excludes encoding and an external database;
process peak RSS is cumulative and Python allocation peaks exclude native memory.
Concurrent development runs cannot establish controlled speed comparisons. Keep
model/view results and descriptive article-cluster intervals separate; report
gains, ties and losses at the declared capacities without a universal leadership
claim.

Markdown paragraph isolation can split an otherwise fitting small document and
ignores soft minimum pressure to recombine body paragraphs. Heading prefixes may
accompany their following body when the full payload fits. More chunks can mean
more stored vectors and embedding/index work, while narrower passages contain
less adjacent context. There is no compact-profile flag or universal cost-saving
claim. Independent review of short-answer labels as complete supporting evidence
and production design-partner evaluation remain open M1 gates.

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
