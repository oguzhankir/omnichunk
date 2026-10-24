# Benchmarks

These scripts measure declared workloads and configurations. Record the commit,
dependency versions, corpus hash/license, platform and optional acceleration with
results. Structural checks and throughput do not establish retrieval quality.

## Retrieval evaluation and tuning

Run the offline baseline from a checkout:

```bash
pip install -e .
python benchmarks/run_retrieval.py --split dev --tools omnichunk,fixed \
  --chunk-sizes 128 256 --unit chars --retrieval-budget 1024 --top-k 5 \
  --repeats 3 --output reports/retrieval-dev.json
```

`benchmarks/retrieval/corpus_v1` contains 30 original synthetic documents and
300 evidence-labeled queries across English, Turkish and Japanese, covering code,
Markdown and tables. Its MIT license, provenance, document hashes and exact UTF-8
evidence spans are recorded with the corpus. Development and test documents are
disjoint. Tune on `--split dev`, freeze the configuration, then run `--split test`
once for the held-out report. Repeatedly choosing settings on test results turns
that split into another development set.

The retriever is a fixed offline character-ngram TF-IDF lexical baseline. Its IDF
is fitted on source documents, keeping it independent of candidate chunk counts.
It performs no embedding-provider calls or model downloads. The authored questions
and answers have not had independent human review; this corpus exercises the
evaluation machinery and does not represent production demand or establish
semantic retrieval quality.

Install optional comparator packages explicitly and select them with `--tools`:

```bash
pip install -r benchmarks/retrieval/requirements.txt  # tested on Python 3.12
python benchmarks/run_retrieval.py --split dev \
  --tools omnichunk,fixed,semchunk,langchain,semantic-text-splitter,chonkie,llamaindex \
  --chunk-sizes 128 256 --output reports/retrieval-comparison.json
```

Every candidate uses the same counter, size capacity, zero overlap and no derived
context. Missing dependencies or unsupported APIs are reported as `unavailable`;
execution failures and invalid output remain visible. An incomplete candidate
cannot contribute a successful aggregate. Actual source slices and emitted
payload sizes are checked before retrieval. Token mode requires an explicit
tokenizer, for example `--unit tokens --tokenizer cl100k_base` after installing
`omnichunk[tiktoken]`; tokenizer assets may need to be cached before an offline run.

Reports include Recall@k, MRR@k and nDCG@k, source-evidence precision/recall/IoU,
fixed-budget evidence retrieval, language/category slices and per-query rankings.
The fixed-budget selection retains a rank prefix, measures the complete joined
context with separators, and stops at the first passage that does not fit.
Chunk-level relevance depends on each candidate's boundaries, so compare it
alongside source-evidence scores rather than treating it as a common set of
retrievable items. Span metrics union overlapping UTF-8 byte intervals per source;
duplicate retrieval does not create additional evidence.

The JSON preserves configuration and corpus/source/dependency fingerprints,
index size, actual payload sizes, repeated timing samples and memory diagnostics.
Python allocation measurements exclude native allocator memory; process peak RSS
is cumulative for the process, not an isolated per-candidate measurement. Compare
repeated runs on the same runner and retain the raw reports. The tool does not
select a universal winning library. See the
[evaluation methodology](../docs/performance/sla.md#retrieval-quality) for metric
interpretation and the remaining M1 acceptance criteria.

CI runs the development comparison on Python 3.12 and uploads its full JSON as
the `retrieval-evaluation` artifact. It validates the experiment rather than
requiring OmniChunk to beat a competing tool. Named tokenizer assets must be
available for a token experiment; their download failure is never replaced with
an approximate counter. Chonkie's count-only token adapter is explicitly
unavailable because its encode/decode contract cannot be inferred from counts.

## Core and structural checks

```bash
python benchmarks/run_benchmarks.py
python benchmarks/run_quality_report.py
python scripts/check_benchmarks.py --run-quality
```

`SCENARIOS` in `run_benchmarks.py` defines local fixtures. Quality checks validate
source reconstruction, coverage and deterministic output; retrieval quality needs
a separate labeled evaluation corpus. Timing varies between runs even when the
chunks are deterministic.

## Optional tool comparisons

```bash
python benchmarks/run_comparisons.py --corpus smoke --save reports/comparison.json
python benchmarks/run_comparisons.py --corpus mega-fixture --no-table
python benchmarks/run_comparisons.py --corpus mega-python --repeat 50
python benchmarks/run_comparisons.py --include-extra
```

The default `all` corpus includes small fixtures and synthetic Python repeated 50
times. `smoke` excludes the large fixture; `mega-fixture` uses only that on-disk
file; `mega-python` generates a temporary corpus with the chosen repeat count.

All supported adapters receive the same character capacity, zero overlap and no
derived context. Token scenarios instead use the same explicit `cl100k_base`
counting function. Semchunk uses the actual requested counter/budget; it no longer
substitutes a quarter-sized word budget. Output sizes are checked for every tool.

Missing dependencies or unsupported APIs report `unavailable`. `--include-extra`
reports ASTChunk as excluded until its units and overlap contract are verified;
the adapter does not guess parameter names and silently accept defaults. Each
scenario has one untimed warmup. Partial scenario totals cannot produce a timing
ratio. The JSON includes per-scenario diagnostics and configuration. Its retained
`winner` field is empty; results are descriptive, and exit status indicates
execution or output-validation failure rather than a speed contest.

Ratios divide competitor elapsed time by Omnichunk elapsed time over the same
complete scenario set. They measure these workloads only. Small fixtures include
substantial call/parse overhead; report larger workloads and repeated samples when
investigating throughput. Parsing structure and producing metadata involve more
work than splitting strings.

## Gutenberg prose

```bash
python benchmarks/run_gutenberg.py
```

Requires NLTK, an already installed Gutenberg corpus, tiktoken vocabulary assets,
and whichever optional comparator packages are used. The script does not download
the corpus. Record corpus provenance/license when distributing results.

Every supported tool uses 512 `cl100k_base` tokens and zero overlap; Omnichunk
renders no derived context. The semantic-text-splitter adapter uses its tokenizer
callback API. Input/output token auditing is outside the splitting timer.

CSV reports source characters, UTF-8 bytes, input tokens, total/mean/maximum output
chunk tokens, overflow count and elapsed time. Throughput uses UTF-8 MiB/s.
`overflow` or `error` produces a nonzero exit code. Unavailable tools are explicit.
Old results from mixed token/character capacities and source-token averages do not
constitute equivalent-budget evidence for this runner.

## Profiling and larger workloads

```bash
python benchmarks/run_large_corpus.py --mode mega-python --repeat 120
python benchmarks/run_large_corpus.py --mode directory --directory ./src --glob "**/*.py"
python benchmarks/run_hotspot_profile.py --mode mega-python --repeat 120 --limit 30
python benchmarks/bench_tfidf_memory.py
python benchmarks/run_v09_stress.py --with-ipynb
python benchmarks/run_html_report.py --output reports/benchmark.html
```

The HTML report loads Chart.js from a CDN. Other runners include dedup/evaluation
stress and optional format cases. Use `--nws-backend auto|python|rust` on the large
corpus runner to inspect acceleration; prefer Python algorithm fixes before native
rewrites. The historical profiling report remains in Git history.

## Prior-release regression gate

```bash
python scripts/check_benchmarks.py --compare-ref v1.0.0 \
  --comparison-report reports/reference.json
```

The gate archives previous source read-only and runs both revisions using one
interpreter, dependency environment, fixture and harness. It uses a 512-character
budget, no context, zero overlap and Python NWS, and records repeated samples,
actual maximum payload sizes and complete reconstruction. Invalid output or
incompatible dependencies fails the comparison instead of asserting speed parity.
Valid comparable baselines allow at most a 10% regression.

For the first 2.x contract transition, the known legacy reference violates the
requested budget. A reviewed transition manifest can establish the new valid
baseline without a speed-parity claim:

```bash
python scripts/check_benchmarks.py --compare-ref v1.0.0 \
  --record-transition-baseline benchmarks/transition_baseline.json \
  --transition-rationale "Describe why the previous contract is not comparable."
python scripts/check_benchmarks.py --compare-ref v1.0.0 --require-baseline \
  --transition-manifest benchmarks/transition_baseline.json --release-tag v2.1.0 \
  --comparison-report reports/release-benchmark.json
```

The manifest binds the specific old revision, corpus/harness/settings and new
behavior source. It is not a general regression bypass; later 2.x releases use a
valid predecessor. Ordinary CI's historical `--run-regression-gate` still explicitly
skips an absent machine-local `baseline.json`; release validation uses the separate
reference gate. Do not commit arbitrary laptop measurements as a universal SLA.
See [performance methodology](../docs/performance/sla.md) and the
[roadmap](../ROADMAP.md) for the remaining evaluation and release criteria.
