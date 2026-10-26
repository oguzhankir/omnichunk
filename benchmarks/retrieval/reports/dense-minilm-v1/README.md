# Frozen multilingual MiniLM comparison

Real pretrained dense evaluation compares released OmniChunk v2.2.0 with recursive-tail packing and a development-discovered orphan-heading repair. Held-out recall ties v2.2.0 at all four settings; synthetic 96-token precision/IoU decline despite fewer chunks. Development outcomes are mixed, and competitor advantages vary. These results do not establish a universal quality or latency advantage. M1 remains open.

## Frozen experiment

| Item | Value |
| --- | --- |
| Baseline | v2.2.0, `fa80b981efa84d1fe8ca1cbb8556aa715c14cb0e`, separate worktree |
| Initial development candidate | `b22b68aafad452c3e187118478a2e0aa3fe1d5af` |
| Final development/held-out source | `a2e3bae7afb9b81f7c044ac0feda6612b0f97c97` |
| Encoder | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Exact model revision | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` |
| Encoder contract | CPU, 384 dimensions, standard Transformer + mean Pooling, empty prompt, cosine normalization in retrieval |
| Input policy | Native snapshot tokenizer; special tokens included; reject truncation/overflow; model limit 128 tokens |
| Chunk/retrieval settings | 64 and 96 token capacities; 512-token complete joined retrieved context; top-k 5; zero overlap; context `none` |
| Execution | Batch size 32; Torch intraop 2 and interop 2; OMP/MKL 2; tokenizer parallelism disabled; Python hash seed 0 |
| Repetition | `--repeats 3` repeats chunking after warmup; encoding prepared once per corpus/runtime; indexing timed once per adapter/capacity; ranking timed once per query per adapter/capacity |
| Freeze | `2026-10-26T10:21:54.542821+00:00`, before the first held-out dense matrix; [freeze record](freeze-before-heldout.json) |

Six adapters share this counter and harness: OmniChunk, fixed source slicing, semchunk, LangChain, semantic-text-splitter and LlamaIndex. Chonkie is explicitly excluded because a count-only token callback does not implement its encode/decode contract. Both source runtimes use the current harness; reports identify the actually imported runtime independently.

`top-k=5` governs the separate ranking and `evidence_at_k` metrics. The main scores below use `evidence_at_budget`: the complete ranked prefix that fits 512 tokens, including separators, which can contain more than five passages. Recall is the fraction of gold UTF-8 source bytes retrieved; precision and IoU use unions of source intervals. Chunk-level relevance sets differ with boundaries.

The model was resolved once, downloaded outside the repository, and verified against the pinned upstream Git/LFS metadata. All 12 selected files, including tokenizer, weights and pooling configuration, have SHA-256 records in [model-manifest.json](model-manifest.json). The 470,641,600-byte `model.safetensors` SHA-256 is `eaa086f0ffee582aeb45b36e34cdd1fe2d6de2bef61f8a559a1bbc9bd955917b`. This is a pretrained-weight experiment, not a randomly initialized smoke test.

Environment: CPython 3.12.14, Linux x86_64, AMD EPYC 9V74 virtual CPU, five available logical CPUs with both Torch pools explicitly limited to two. Encoder packages are Torch 2.14.1+cpu, sentence-transformers 6.2.0, transformers 5.20.2 and huggingface-hub 2.3.0. Comparators use the repository's pinned requirements. The [environment records](environment/) fingerprint 172 installed distributions, Python/platform/CPU and editable source files. These are hashes of installed bytes, not upstream wheel archives. The frozen installed-package manifest SHA-256 is `b0bd33ecd41d17f690dbe24e1907c5c3eec973021aadb7896c9cb84ddc997a1c`.

## Development decision

Development uses 180 synthetic English/Turkish/Japanese queries and 48 independent English SQuAD-subset queries. Initial tail-only development preserved every synthetic score at both capacities. On external 64-token prose it reduced chunks 69→64, kept recall 0.979167 and modestly improved precision/IoU; external 96-token recall also stayed unchanged.

Inspection of development failures against LangChain exposed a general structural defect: an oversized Markdown body flushed its fitting pending heading before recursive splitting. Ten synthetic Markdown/table titles became standalone chunks at both capacities. The repair attaches a heading to fitting following content while preserving exact source ranges, heading metadata, complete-input budgets and protected fences. It does not add corpus-, language- or query-specific rules.

Retain both repairs. The final synthetic 64-token run gains two recall queries; 96 tokens loses one. The latter retains its gold paragraph intact, but adding the fitting title changes its embedding ranking and moves it beyond the selected context prefix. This tradeoff is disclosed rather than used to choose a special case or a preferred capacity. Source/model/settings were then frozen before held-out evaluation.

| Development corpus / tokens | Recall before→after | Chunks before→after |
| --- | --- | --- |
| Synthetic / 64 | 0.901598→0.912709 | 211→208 |
| Synthetic / 96 | 0.900070→0.894515 | 125→119 |
| External / 64 | 0.979167→0.979167 | 69→64 |
| External / 96 | 0.979167→0.979167 | 45→45 |

Paired complete-context evidence metrics follow. W/T/L counts per-query candidate wins, ties and losses; intervals are deterministic 95% percentile intervals from 2,000 gold-source connected-component resamples, seed 0.

| Corpus / tokens | Metric | Baseline | Candidate | Delta | W/T/L | 95% delta interval |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | Recall | 0.901598 | 0.912709 | +0.011111 | 2/178/0 | [0, 0.033333] |
| Synthetic / 64 | Precision | 0.080311 | 0.081264 | +0.000953 | 45/95/40 | [-0.000028, 0.002466] |
| Synthetic / 64 | IoU | 0.080006 | 0.080961 | +0.000954 | 45/95/40 | [-0.000028, 0.002466] |
| Synthetic / 96 | Recall | 0.900070 | 0.894515 | -0.005556 | 0/179/1 | [-0.016667, 0] |
| Synthetic / 96 | Precision | 0.084391 | 0.084118 | -0.000273 | 19/139/22 | [-0.001229, 0.000415] |
| Synthetic / 96 | IoU | 0.084336 | 0.084063 | -0.000273 | 19/139/22 | [-0.001229, 0.000415] |
| External / 64 | Recall | 0.979167 | 0.979167 | 0 | 0/48/0 | [0, 0] |
| External / 64 | Precision | 0.012603 | 0.012791 | +0.000189 | 25/15/8 | [0.000009, 0.000392] |
| External / 64 | IoU | 0.012603 | 0.012791 | +0.000189 | 25/15/8 | [0.000009, 0.000392] |
| External / 96 | Recall | 0.979167 | 0.979167 | 0 | 0/48/0 | [0, 0] |
| External / 96 | Precision | 0.012881 | 0.012891 | +0.000010 | 2/45/1 | [-0.000007, 0.000036] |
| External / 96 | IoU | 0.012881 | 0.012891 | +0.000010 | 2/45/1 | [-0.000007, 0.000036] |

The synthetic recall changes are Turkish Markdown: `tr/knowledge_approval/q08` and `q10` improve 0→1 at 64; `tr/import_workflow/q02` declines 1→0 at 96. Turkish and Markdown slices respectively change +0.033333 at 64 and -0.016667 at 96; English, Japanese, code and table recall are unchanged. Full slice metrics, intervals and all precision losses remain in paired JSON; the aggregate improvement does not mean every query improved.

Development controls match across rounds: every baseline and rival has identical passages, selected rank IDs, query quality metrics and aggregates. A few synthetic candidate rival cosine values differ by at most 1.876e-7 with changed shared batch composition; no ranking or quality result changes. External baseline/candidate results are exactly identical across the two rounds because its plain-text inputs do not use the heading repair.

## Development competitors

All entries are final candidate-runtime complete-context evidence recall; no capacity was selected from these scores.

| Adapter | Synthetic 64 | Synthetic 96 | External 64 | External 96 |
| --- | --- | --- | --- | --- |
| OmniChunk | 0.912709 | 0.894515 | 0.979167 | 0.979167 |
| Fixed | 0.835434 | 0.830459 | 1.000000 | 0.979167 |
| semchunk | 0.917331 | 0.900000 | 0.999707 | 0.979167 |
| LangChain | 0.927082 | 0.888889 | 0.949359 | 0.970192 |
| semantic-text-splitter | 0.917913 | 0.900000 | 0.979167 | 0.979167 |
| LlamaIndex | 0.817761 | 0.882670 | 0.961806 | 0.961806 |

OmniChunk exceeds fixed and LlamaIndex on synthetic recall but trails LangChain at 64 and semchunk/semantic-text-splitter at both capacities. On external 64 it trails fixed and semchunk; at 96 it ties several adapters in recall while fixed has higher precision. The raw rival comparisons retain paired confidence intervals and wins/losses, ranking@5, precision/IoU and language/category slices. No single adapter wins across these experiments.

## Held-out results

Both published test splits were evaluated once after the recorded freeze: 120 synthetic queries and 48 external queries. All four complete-context recall means are unchanged. Chunk counts fall 150→148 and 89→86 for synthetic 64/96, and 69→66 and 44→44 for external 64/96. No source or setting was changed from these test outcomes.

| Corpus / tokens | Metric | Baseline | Candidate | Delta | W/T/L | 95% delta interval |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic / 64 | Recall | 0.954850 | 0.954850 | 0 | 0/120/0 | [0, 0] |
| Synthetic / 64 | Precision | 0.085497 | 0.085386 | -0.000111 | 5/103/12 | [-0.000258, 0.000050] |
| Synthetic / 64 | IoU | 0.085194 | 0.085085 | -0.000109 | 5/103/12 | [-0.000253, 0.000050] |
| Synthetic / 96 | Recall | 0.951008 | 0.951008 | 0 | 0/120/0 | [0, 0] |
| Synthetic / 96 | Precision | 0.092787 | 0.092084 | -0.000704 | 7/91/22 | [-0.001175, -0.000337] |
| Synthetic / 96 | IoU | 0.092636 | 0.091932 | -0.000704 | 7/91/22 | [-0.001175, -0.000337] |
| External / 64 | Recall | 1.000000 | 1.000000 | 0 | 0/48/0 | [0, 0] |
| External / 64 | Precision | 0.008456 | 0.008440 | -0.000016 | 16/15/17 | [-0.000097, 0.000067] |
| External / 64 | IoU | 0.008456 | 0.008440 | -0.000016 | 16/15/17 | [-0.000097, 0.000067] |
| External / 96 | Recall | 1.000000 | 1.000000 | 0 | 0/48/0 | [0, 0] |
| External / 96 | Precision | 0.008879 | 0.008879 | 0 | 0/48/0 | [0, 0] |
| External / 96 | IoU | 0.008879 | 0.008879 | 0 | 0/48/0 | [0, 0] |

The synthetic 96-token precision/IoU loss has a descriptive interval wholly below zero and must not be presented as a quality improvement. Every language/category recall slice is unchanged. Its precision losses span English -0.000562, Turkish -0.000713 and Japanese -0.000836; code -0.000062, Markdown -0.000770 and tables -0.001177. At 64, Markdown precision gains +0.000046 while code/table precision decline; all language precision means decline slightly. External 64 precision is mixed by query, and external 96 source-evidence metrics tie exactly. Full per-query and slice intervals are retained in the raw reports.

Ranking recall@5 also stays unchanged versus baseline at all settings. MRR@5 changes from 0.872917→0.877778 and 0.807778→0.810556 on synthetic 64/96, and 0.895833→0.885417 on external 64; external 96 ties. nDCG@5 follows the same mixed directions. These chunk-level ranking metrics use boundary-dependent relevance and do not override the common source-evidence comparison.

| Adapter | Synthetic 64 | Synthetic 96 | External 64 | External 96 |
| --- | --- | --- | --- | --- |
| OmniChunk | 0.954850 | 0.951008 | 1.000000 | 1.000000 |
| Fixed | 0.877481 | 0.896307 | 1.000000 | 1.000000 |
| semchunk | 0.954597 | 0.966667 | 1.000000 | 1.000000 |
| LangChain | 0.955650 | 0.958333 | 0.989247 | 1.000000 |
| semantic-text-splitter | 0.955423 | 0.966667 | 1.000000 | 1.000000 |
| LlamaIndex | 0.879162 | 0.907942 | 0.979167 | 1.000000 |

Held-out synthetic 64 recall is close among OmniChunk, semchunk, LangChain and semantic-text-splitter; OmniChunk trails the latter two slightly. At 96 it trails semchunk/semantic-text-splitter and LangChain, while exceeding fixed and LlamaIndex. External 64 recall ties several adapters and exceeds LangChain/LlamaIndex; all adapters tie external 96 recall. Tied recall does not imply tied precision or cost: fixed has higher external precision than OmniChunk at both capacities. No leadership claim is supported.

Independent checks match final-development and held-out source revisions, model-file hashes and encoder-package versions. Both held-out candidate runtimes are clean at the frozen source; their source fingerprint is `1e97c0fdbe8a3a1c025948bb7094a8b54db0ecb8223c9b5e51189153dad916f7`, identical to final development and the current Python source bytes. Baseline source fingerprints also match across all runs. The original implementation decision remains based on development; no held-out tuning or replacement run was performed.

## Workload and measured cost

The table reports whole preparation passes shared across all six adapters and both capacities. Each pass deduplicates passage payloads within its role; these durations are not attributable to one chunker or independent online query encoding.

| Corpus / runtime | Unique passages / queries | Passage / query tokens | Encoder batches | Encode seconds | Load seconds | Process peak RSS GiB |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic dev baseline | 1655 / 180 | 86880 / 3300 | 52 + 6 | 53.385 | 1.672 | 1.594 |
| Synthetic dev candidate | 1653 / 180 | 86945 / 3300 | 52 + 6 | 60.582 | 1.764 | 1.598 |
| External dev baseline | 742 / 48 | 27860 / 742 | 24 + 2 | 26.338 | 1.691 | 1.515 |
| External dev candidate | 734 / 48 | 27682 / 742 | 23 + 2 | 23.869 | 2.099 | 1.516 |
| Synthetic test baseline | 1172 / 120 | 60332 / 2240 | 37 + 4 | 35.128 | 1.731 | 1.570 |
| Synthetic test candidate | 1171 / 120 | 60407 / 2240 | 37 + 4 | 39.533 | 1.768 | 1.563 |
| External test baseline | 742 / 48 | 27668 / 785 | 24 + 2 | 25.465 | 1.924 | 1.501 |
| External test candidate | 737 / 48 | 27574 / 785 | 24 + 2 | 25.601 | 1.819 | 1.502 |

Snapshot hashing and token-validation time are separate in producer metadata. RSS is the cumulative process high-water mark before vector serialization, including native allocations, not isolated encoder memory or per-adapter memory. Encoder timings include first-call/native-batching effects and have one sample per runtime; they do not establish an encoding speedup.

| Corpus / tokens | OmniChunk passage tokens before→after | Chunking median seconds before→after | Frozen ranking/query median ms before→after |
| --- | --- | --- | --- |
| Synthetic dev / 64 | 8857→8851 | 0.252→0.359 | 5.057→5.280 |
| Synthetic dev / 96 | 8685→8673 | 0.174→0.207 | 2.858→2.812 |
| External dev / 64 | 3040→3030 | 0.178→0.177 | 1.678→1.462 |
| External dev / 96 | 2992→2992 | 0.120→0.113 | 1.445→1.057 |
| Synthetic test / 64 | 6177→6173 | 0.174→0.271 | 3.452→3.631 |
| Synthetic test / 96 | 6055→6049 | 0.128→0.164 | 1.982→2.078 |
| External test / 64 | 2998→2992 | 0.178→0.165 | 1.582→1.523 |
| External test / 96 | 2948→2948 | 0.098→0.111 | 0.971→1.100 |

These passage-token counts describe hypothetical per-adapter embedding input, including special tokens, not independently measured bills. All evaluation embedding-call counts are zero. Frozen ranking/query time includes frozen-vector lookup/cosine ranking; it excludes encoding, context-budget selection, evidence scoring, external vector databases and network latency. Index construction has one timed sample per adapter/capacity. Chunking has three timed samples after warmup, with a separate memory pass; do not infer production latency from these small workloads.

## Validation

The frozen implementation passed 1,388 tests with 36 optional skips and 90.78% branch coverage, Ruff, required formatting, strict mypy and five structural quality scenarios. Strict MkDocs, wheel/sdist metadata checks and an isolated minimal installed-wheel smoke also passed. The source commit passed GitHub CI and a code-bot rereview with no findings. Each held-out report passed 76 provenance assertions; a final 97-check freeze audit rehashed the model, all 46,722 installed distribution files and editable source without changes. Security review status is tracked on [PR #35](https://github.com/oguzhankir/omnichunk/pull/35).

## Evidence, reproduction and limits

`initial-dev-*` preserves the tail-only discovery run; `dev-*` preserves final development; `test-*` preserves the single frozen held-out matrix. Each contains compressed baseline/candidate reports, experiment settings, paired/rival comparisons, preparation logs and provenance checks. Frozen vector artifacts are retained outside the repository; their artifact hashes remain in the raw reports, and the pinned snapshot/producer can regenerate them. Model weights also remain outside the repository. [freeze-before-heldout.json](freeze-before-heldout.json), [model-manifest.json](model-manifest.json) and [environment/](environment/) bind the development decision to the source/model/environment.

The freeze record keeps original experiment paths: `dev2-corpus_*` is stored here as `dev-corpus_*`. Some original `.json` files are stored as `.json.gz`; decompress those to verify their original freeze hashes. Reports already named `.report.json.gz` were copied byte-for-byte and keep their compressed-file hashes. The installed-package manifest hash likewise covers its decompressed JSON. [evidence-sha256.json](evidence-sha256.json) fingerprints the exact stored bytes of every evidence file except itself.

From the repository root, reproduce using an explicitly cached pinned snapshot and a separate v2.2.0 worktree:

```bash
git worktree add --detach /tmp/omnichunk-baseline fa80b981efa84d1fe8ca1cbb8556aa715c14cb0e
python benchmarks/run_dense_experiment.py \
  --model-dir /path/to/pinned/snapshot \
  --model-revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42 \
  --baseline-dir /tmp/omnichunk-baseline --corpus corpus_v1 --split dev \
  --output-dir /path/to/empty/results
```

Use the frozen source and installed package versions; repeat for `corpus_squad_v1`. The helper never downloads a model. Reports validate the actual baseline/candidate revisions, clean source, shared harness/model/package hashes, both observed Torch pools and input/context capacities. The source freeze and original test run should remain the reported experiment; a later reproduction does not become another tuning opportunity.

Synthetic data is original MIT-licensed assistant-authored evaluation material; its questions and labels are not independently human-audited. SQuAD 1.1 contains independently authored questions but this small English subset and its exact answer spans are not a complete-evidence audit. External source text and reproduced report passages retain CC-BY-SA-4.0 attribution to Wikipedia contributors and SQuAD authors; see the corpus manifests/README. Benchmark software remains MIT.

Published document/article-disjoint splits have earlier lexical results and are not independently sealed. Gold-source bootstrap components keep questions sharing a source together, but paragraphs from one article can remain correlated. Intervals are descriptive, unadjusted for multiple comparisons or development selection; small corpora, one encoder, no production workload and no downstream answer-generation evaluation limit inference. M1 still requires independent review of selected supporting-evidence suitability and production design-partner validation. No release, merge or M3/M4 completion is implied.
