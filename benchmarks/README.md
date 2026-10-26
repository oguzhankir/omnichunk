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

### Independent source data

`retrieval/corpus_squad_v1` contains a frozen, attributed CC-BY-SA-4.0 subset of
SQuAD 1.1: 32 Wikipedia paragraphs and 96 human-annotated questions. Its development
and test splits separate entire articles. The original SQuAD development file is
the upstream source; these local splits are not the official SQuAD leaderboard.
See the corpus README for selection, attribution and licensing.

```bash
python benchmarks/run_retrieval.py --corpus benchmarks/retrieval/corpus_squad_v1 \
  --split dev --tools omnichunk,fixed,semchunk,langchain,semantic-text-splitter,chonkie,llamaindex \
  --chunk-sizes 128 256 --repeats 3 --require-all --output reports/squad-dev.json
```

Rebuild only from an explicitly downloaded upstream file:

```bash
python benchmarks/import_squad.py --input /path/to/dev-v1.1.json --output /tmp/squad-corpus
```

The importer verifies a pinned upstream SHA-256 before selecting records and
never downloads data. Corpus validation rejects duplicate JSON keys, non-finite
numbers and Unicode/whitespace-equivalent documents or questions crossing splits.
The independent corpus covers English prose; synthetic code/table/multilingual
fixtures remain separate. Neither dataset establishes a production-wide ranking.

Frozen full external reports are in `retrieval/reports/squad-lexical-{dev,test}-v1.json.gz`.
They were measured from clean source commit `a8216af`, retain all per-query ranks
and passages, and can be opened with Python's `gzip.open` and `json.load`. Source
passages reproduced inside these reports retain the external corpus's
CC-BY-SA-4.0 license and attribution; the benchmark software remains MIT licensed.

### Frozen dense retrieval

Use `--retriever dense --dense-embeddings /path/to/vectors.json` with the same
runner settings to replace lexical retrieval. The versioned artifact binds each
query/passage role and exact UTF-8 payload hash to a finite vector, a corpus hash,
model revision and preprocessing revision. Missing payloads, inconsistent dimensions
or incompatible corpus hashes fail the experiment. Reports retain the artifact
hash and producer metadata; evaluation makes zero model calls.

`benchmarks/prepare_dense.py --help` describes preparation using an explicitly
cached, local SentenceTransformer model. Install `sentence-transformers` separately;
it is not a library dependency. The producer records local model file hashes and
rejects overflowing inputs instead of silently truncating them. Supported local
models use the documented symmetric encoder contract; role-specific encoders can
use `build_dense_artifact` with an explicit callback and preprocessing revision.
An artifact records producer assertions and cannot independently attest how an
external producer generated vectors.

No pretrained dense-model result is included in this change: the execution
environment blocks HuggingFace downloads. Unit-test vectors and randomly initialized
local models validate plumbing only. A pretrained dense comparison, independent
review of selected answer evidence and production design-partner evaluation remain
M1 acceptance work.

### Baseline/candidate dense experiments

`run_dense_experiment.py` orchestrates the current evaluation harness against an
isolated baseline checkout and the candidate. It requires an already downloaded
local snapshot and an explicit model commit. It never downloads a model itself.

```bash
git worktree add --detach /tmp/omnichunk-baseline v2.2.0
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false \
python benchmarks/run_dense_experiment.py \
  --model-dir /path/to/frozen/snapshot --model-revision MODEL_COMMIT_SHA \
  --baseline-dir /tmp/omnichunk-baseline --corpus corpus_v1 --split dev \
  --output-dir reports/dense-synthetic-dev
```

The declared encoder is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
Both runtimes use the same model, native tokenizer (including special tokens),
64/96-token chunk capacities, 512-token retrieved context, top-k 5, zero overlap
and no derived context. Repeat for `--corpus corpus_squad_v1`. Six token-safe
adapters run; Chonkie's count-only token contract remains explicitly excluded.
The actual imported runtime has its own git revision/dirty status and source hash,
separate from the shared harness. A source checkout must be available for the baseline.

`.github/workflows/dense-evaluation.yml` offers the same experiment on hosted
CPU runners with pinned package versions and separate report/vector artifacts.
It is **manual only**: no push, PR or release starts model downloads. GitHub must
first have this workflow on its default branch before dispatch is available.
Development discovery may resolve a model revision once for both corpus jobs;
held-out dispatch requires its explicit 40-character commit. Freeze the source,
model, tokenizer and capacities before selecting `test`; never tune from that run.

```bash
python benchmarks/compare_retrieval.py --baseline before.json.gz \
  --candidate after.json.gz --output reports/paired.json
```

The paired report requires matching corpus, query/evidence labels, budgets and
model/snapshot/package provenance. It retains language/category slices and
wins/ties/losses, with deterministic 95% percentile intervals from gold-source
connected-component resampling. Queries sharing a source stay together. Fewer
than two components yields no interval. Articles can still correlate across
paragraphs; these descriptive intervals do not correct selection or establish
production leadership.

Encoder preparation records global per-role batches, native token counts, timings,
CPU thread settings, producer hashes and process-lifetime RSS. Shared preparation
deduplicates across candidates: its cost is not attributable to one chunker.
Candidate payload/token workloads describe potential work, not measured independent
embedding bills. Frozen-vector index/query latency excludes encoding and any
external vector database. Python incremental index memory excludes native allocations.

The recursive-tail repair has development-only lexical evidence: external recall
at 256 characters changes from 0.916667 to 0.937500 with 72 to 68 chunks; at 128
it stays 0.918841 with 136 to 126 chunks. Synthetic recall at 128 changes from
0.925479 to 0.925122 (one Turkish approval-matrix loss); 256 stays 0.982405.
These are character-budget lexical controls, not native-token dense results.
No pretrained or held-out result has been produced for this repair. Keep or revise
the repair based on dense development evidence before freezing a held-out run.

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
