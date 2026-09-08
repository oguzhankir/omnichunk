# Omnichunk roadmap: 2.0 foundations, 3.0 maturity, 4.0 vision

Audited **2026-09-08** against `fc96425`; implementation subsequently completed in
this working tree through the **2.1.0** milestone. The 2.0 foundations and 2.1 code
improvements will be delivered together in the maintainer's next 2.1.0 release.
This document distinguishes implemented work, verification and future plans;
it does not announce publication. Documentation stays in English for contributors.

**Direction:** make Omnichunk a dependable chunking library for code and mixed
documents, with verifiable source references, predictable token budgets, safe
incremental indexing, and demonstrated retrieval quality.

**Release shape:** one substantial foundation transition in **2.0.0**;
backward-compatible improvements throughout **2.x**; a narrowly scoped **3.0.0**
compatibility checkpoint; research-led extensions through **3.x** toward **4.0.0**.
The version numbers express compatibility, not a requirement to invent rewrites.

### Implementation status: through 2.1.0

| Workstream | Implemented behavior | Evidence |
| --- | --- | --- |
| 2.0-A configuration/tooling | Validated immutable options, one version source, optional core dependencies, no coverage omissions, normal-CI Hypothesis and licensed frozen corpus | `config.py`, `pyproject.toml`, `benchmarks/corpus.json`, `tests/test_v2_contracts.py`, `tests/test_conformance_corpus.py` |
| 2.0-B source/schema | Canonical UTF-8 descriptors, full metadata serialization, rebased nested ranges, lossless/retrieval policies and omission manifest | `finalize.py`, `serialization.py`, `context/rebase.py`, `tests/test_v2_persistence.py`, `tests/test_v2_parser_formats.py` |
| 2.0-C finalization | Explicit token provider, final rendered budget enforcement, measured overflow, shared overlap across sync/stream/semantic/document APIs | `finalize.py`, `protocols.py`, `tests/test_v2_finalization_review.py` |
| 2.0-D indexing | Content/occurrence IDs, separate payload/config fingerprints, atomic scoped collections, failure rollback and conservative opaque-provider invalidation | `diff/`, `store/`, `semantic/cache.py`, `tests/test_v2_persistence.py`, `tests/test_semantic_cache.py` |
| 2.0-E delivery | Bounded async output and export batches, isolated registries, constrained RPC, legacy readers and separate-index migration examples | `tests/test_v2_execution.py`, `tests/test_mcp_server.py`, [migration guide](docs/migrations/v2.md) |
| 2.1 code quality | Capability matrix, fallback diagnostics, decorators/comments/generics/nested scopes, mixed fences and interval-based entity lookup | `parser/languages.py`, `context/range_index.py`, `tests/test_v2_source_code.py` |

Public behavior is documented in the [contract reference](docs/reference/contracts.md).
The implementation retains source/AST memory; context can be omitted to meet the
final budget; arbitrary callbacks have cooperative cancellation. Internal typed
pipeline protocols do not imply that every stage is publicly replaceable.

**Release handoff:** version metadata/runtime now share
`src/omnichunk/_version.py` (still `1.0.0` pending the maintainer's requested bump).
Set it to `2.1.0` after the final checks, then tag/release through the artifact
validation workflow. No existing tag was modified and nothing was published.
The hosted Python/OS CI matrix must pass on the final commit; local results below
do not stand in for that matrix.

### Local verification: implemented 2.1 candidate

Verified on macOS with Python **3.12.11**, Ruff **0.15.12** and mypy **1.20.2**:

- Full suite: **848 passed, 12 skipped**. Normal runs include bounded Hypothesis
  invariants. Optional integrations retain explicit skips; this is not the hosted
  Python 3.10–3.13 / Linux–macOS–Windows matrix.
- **91.22% aggregate line-and-branch coverage**, with no module omissions:
  **93.70% lines**, **84.81% branches**. The configured 90% gate passes.
- Ruff lint/format, strict mypy over **84 source files**, five synchronized AI
  rule files, strict MkDocs and **78 local Markdown links/anchors** pass.
- All **12 example scripts** execute. The contract and migration examples include
  Unicode/CRLF text and notebook index rebuilds, metadata/citation validation,
  independent old/new stores and rollback.
- Five structural benchmark scenarios pass. Installed Omnichunk/semchunk
  comparisons pass four equal-character-budget smoke workloads. Real cl100k
  vocabulary assets were unavailable locally; token adapter contract tests use
  deterministic tokenizer stubs, not a claimed downloaded-model benchmark.
- Wheel and sdist build; strict Twine validation and an isolated dependency-free
  wheel installation pass. Packaged Python source matches the checkout and
  package/runtime both report the intentionally unbumped **1.0.0**.
- `benchmarks/transition_baseline.json` records the one-time contract transition:
  the old v1 reference emits **768** characters for a requested **512**; this
  candidate emits at most **501** with complete source reconstruction. The old
  run is retained as invalid for speed comparison. The bound manifest establishes
  a new baseline without claiming speed parity; later 2.x releases compare to a
  valid predecessor on the same runner.

Reproduce the full coverage gate with:

```bash
pytest -q --cov=src/omnichunk --cov-branch --cov-report=term-missing --cov-fail-under=90
```

The transition report is bound to behavior source, project configuration, corpus
and harness. Regenerate it after changes to those inputs; a version-only edit to
`_version.py` is allowed. Hosted matrix results and the real 2.1.0 tag/artifacts
remain release-time checks. Full retrieval quality, large-corpus peak-RSS studies
and universal performance superiority have not been established by these tests.

## 1. Feature inventory at the original audit

The pre-transition repository already had considerable breadth. The table records
that baseline and its limitations; the implementation status above supersedes
those limitations where fixed. Future work reuses these features.

| Area | Implemented in this checkout | Practical boundary |
| --- | --- | --- |
| Structural chunking | Code, prose/Markdown, markup and hybrid engines; AST entities, scopes, imports, siblings; fenced-block delegation | Engine-specific sizing, fallback and overlap behavior still diverge |
| Code languages | Six bundled grammars: Python, JavaScript, TypeScript, Rust, Go, Java; optional C/C++/C#, Ruby, PHP, Kotlin, Swift, SQL, Bash, Scala, Elixir | Detection, grammar availability and extraction quality are separate capabilities; a `Language` literal is not proof of full parser support |
| Documents | JSON/YAML/TOML, HTML/XML, Markdown/plaintext, RST, notebooks, LaTeX; optional PDF/DOCX loaders | PDF/DOCX are text extraction, not an OCR/layout engine; loaded-document offsets refer to canonical extracted text |
| Semantic tools | User embeddings, adaptive boundary detection, embedding validation/cache, local sentence-transformers helper, dense/sparse TF-IDF, MMR reranking | Some exposed options are not wired into execution; providers and cache identity need a reliable contract |
| Retrieval building blocks | Hierarchy, chunk diff, token budget selection, exact/near deduplication, entity graph with centrality/communities | These are utilities, not an end-to-end GraphRAG retrieval system; incremental correctness has release blockers |
| Propositions | Heuristic extraction and callback-based LLM extraction with batching, iteration, retry/timeout controls | Model-derived claims and context need explicit provenance and reproducibility rules |
| Delivery | CLI, sync/async/batch/iterators, SQLite `ChunkStore`, JSONL/CSV, framework document conversion, vector row serializers, parser/formatter registry, OpenTelemetry | Export is not a database write; iterator output is not necessarily bounded-memory processing |
| Serving | Local HTTP JSON-RPC tools behind `serve --mcp` | This is not a conformant MCP server: initialization and standard tool discovery/calls are absent |
| Engineering | Typed Python package, pytest/Hypothesis, Ruff/mypy, CI, MkDocs, benchmark runners, optional Rust kernels | Coverage excludes key modules; important property tests are marked `slow`; historical performance comparisons are not equivalent-budget evidence |

Implementation map: [architecture](ARCHITECTURE.md),
[examples](examples/README.md), [benchmark instructions](benchmarks/README.md).

### Historical release bookkeeping

`pyproject.toml` declares **1.0.0**, the local **v1.0.0** tag exists, and
`omnichunk.__version__` still reports **0.10.1**. The historical changelog has no
1.0 entry. These observations do not establish the current PyPI release state.
Recent semantic, graph and proposition commits are present after the 1.0 tag.
The implementation now unifies version metadata without rewriting the old tag or
inventing an absent changelog entry. Post-tag work stays under `Unreleased` until
the maintainer cuts the new release.

## 2. What is poorly designed, and why it matters

These are historical findings from source inspection and local reproductions
before the implementation above. P0 means silent loss or stale downstream data;
P1 blocks the 2.0 contract; P2 is a scaling or usability issue. F01–F09 now have
behavioral fixes and regressions; F10 has full coverage/artifact/baseline gates;
F11 has bounded output with explicit per-document costs; F12 has byte-union
coverage and indexed entity lookups. Full retrieval evaluation remains 2.7 work.

| ID | Priority | Evidence before the transition | Implemented target |
| --- | --- | --- | --- |
| F01 | P0 | [`stable_chunk_id`](src/omnichunk/serialization.py) hashes path/index/range, not content; [`chunk_diff`](src/omnichunk/diff/engine.py) compares ID sets. Changing `a = 1\n` to `a = 2\n` reports one unchanged chunk, no additions/removals | Separate identity from content/revision fingerprints; changed content always invalidates its embedding |
| F02 | P0 | [`ChunkStore`](src/omnichunk/store/chunk_store.py) deletes stored paths outside the current scan; syncing one file removed its cached sibling. A chunking failure can replace valid cache data with an empty successful entry | Explicit collection/root ownership, scoped deletion, atomic commit, failure rollback and retry |
| F03 | P1 | Store skips unchanged files after options change; query orders hashed IDs, producing indexes such as `[5, 2, 3, 0, 1, 4]` | Config/parser/tokenizer fingerprints invalidate cache; results have defined source ordering |
| F04 | P1 | [`CodeEngine`](src/omnichunk/engine/code_engine.py) uses approximate sizing; final overlap/merging has no common exact budget validation. With a 40-character limit, a reproduction yielded 69 characters, or 325 with overlap | Shared final budget enforcement, including rendered context and overlap; explicit treatment of indivisible units |
| F05 | P1 | [`_coerce_option_dict`](src/omnichunk/chunker.py) drops unknown keys; `max_size=1` retains the default 1500. Several preservation/semantic options are declared but unused. [`tokenizers.py`](src/omnichunk/sizing/tokenizers.py) silently falls back to word counts | Validate configuration and provider capabilities; never label word estimates as exact model tokens |
| F06 | P1 | [`chunk_from_dict`](src/omnichunk/serialization.py) loses imports, scope, siblings, headings and diagnostics on round-trip | Versioned complete serialization and migration fixtures for persisted chunks |
| F07 | P1 | [`EmbeddingCache`](src/omnichunk/semantic/cache.py) keys only on text. Switching a shared chunker's embedder from 2D to 3D reused the old vectors without calling the new provider; cache is not thread-safe | Provider/model/revision/preprocessing namespace; defined concurrency behavior; dimension validation on cache hits |
| F08 | P1 | [`formats/chunk.py`](src/omnichunk/formats/chunk.py) and hybrid rebasing update chunk ranges but not all nested entity ranges; a notebook function remained at byte 0 when its enclosing segment began at byte 9. Loader warnings can disappear | One coordinate system per declared source; nested metadata rebased and diagnostics retained |
| F09 | P1 | [`mcp/server.py`](src/omnichunk/mcp/server.py) accepts filesystem paths without allowed-root checks, has no Origin/authentication/body-size policy, and exposes custom JSON-RPC methods rather than MCP lifecycle | Isolate and accurately name experimental RPC; constrain filesystem access and requests; real MCP requires protocol conformance tests |
| F10 | P1 | [`pyproject.toml`](pyproject.toml) omits chunker/engines/parser/splitting/tokenizers from coverage; throughput gate passes without a baseline; release workflow builds/publishes without verifying tag/package/runtime versions | Honest coverage denominator, reproducible benchmark baseline and artifact-based release checks |
| F11 | P2 | [`stream_upsert`](src/omnichunk/chunker.py) materializes per-file chunks; semantic and document iterators buffer results; async queue is unbounded | Document memory costs and supported streaming modes; bounded queue, backpressure and cancellation |
| F12 | P2 | [`eval.py`](src/omnichunk/eval.py) calls token containment “coverage,” can return 1.0 when a suffix is omitted, uses ASCII tokenization and repeatedly scans source; code context scans all entities per chunk | Source-span union coverage, multilingual evaluation, indexed interval queries and measured complexity |

The original design rules also conflicted with themselves: universally dropping whitespace
while promising full contiguous reconstruction is impossible for whitespace-only
input; calling the core dependency-free conflicts with mandatory NumPy and grammar
wheels. The implemented policies resolve these conflicts; all five AI rule copies
now describe lossless/retrieval coverage and optional dependencies consistently.

### Local verification snapshot: original audit

Python **3.12.11**, Ruff **0.15.12**, mypy **1.20.2**, local macOS checkout:

- Default suite: **492 passed, 14 skipped, 4 deselected**. Optional dependencies
  and normal `not slow` selection limit the exercised paths; this is not the CI
  Python/OS matrix. Local HTTP tests required execution outside the network sandbox.
- The four normally excluded Hypothesis tests were then run explicitly with
  `pytest -q -m slow tests/test_invariants_hypothesis.py`: **4 passed**. Their
  selected properties do not cover all of the contract defects listed above.
- Coverage with no module omissions: **83.42% combined line+branch**, consisting
  of **86.62% lines** and **75.08% branches**. The command overrides coverage config
  and disables the threshold only to measure the baseline; project settings remain.
- Ruff lint and strict package mypy pass. Format check reports **41 files** needing
  formatting under this local Ruff version; pin tooling before a separate cleanup.
- AI rule synchronization and all **five** benchmark invariant scenarios pass.
- Strict MkDocs build and **69 relative Markdown links/anchors** pass after
  consolidation; the README quick-start source slices were also verified.

Reproduce the coverage denominator independently of `pyproject.toml` exclusions:

```bash
printf '[run]\nbranch = True\nsource = omnichunk\n' > /tmp/omnichunk-full-coverage.ini
pytest -q --cov=omnichunk --cov-branch \
  --cov-config=/tmp/omnichunk-full-coverage.ini --cov-report=term \
  --cov-fail-under=0
```

These historical results are retained for comparison. The implementation removes
the coverage exclusions and keeps the configured 90% gate.

## 3. Competitive position

Primary documentation checked on 2026-09-08. This is a capability comparison,
not a speed ranking, and does not prove competitors lack any proposed guarantee.

| Reference | Existing strength | Implication for Omnichunk |
| --- | --- | --- |
| [Chonkie](https://docs.chonkie.ai/oss/chunkers/overview) and [pipelines](https://docs.chonkie.ai/oss/pipelines) | AST code, sentence, recursive, semantic, late, neural and table chunking, with pipeline composition | Compete on trustworthy behavior and coherent APIs; algorithm count alone is weak differentiation |
| [text-splitter / semantic-text-splitter](https://github.com/benbrandt/text-splitter) | Rust with Python bindings, Unicode/Markdown/code structure, token/custom capacity sizing | Structure and native speed are established capabilities; publish equivalent-budget comparisons |
| [LangChain](https://docs.langchain.com/oss/python/integrations/splitters/index) | Recursive, token, code, Markdown, JSON and HTML splitters | Compare appropriate strategies; offer a native adapter rather than only conversion snippets |
| [LlamaIndex](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/) | Semantic splitting, sentence windows, hierarchical nodes and retriever integration | Make source references and parent/child relationships portable and test their preservation |
| [Docling](https://docling-project.github.io/docling/concepts/chunking/) | Document structure, tokenizer-aware hierarchical refinement and separate contextualization | Integrate existing document extraction; retain page/element provenance instead of building OCR |

The opportunity is **code and mixed-document indexing that remains correct after
edits and through serialization, enrichment and export**. “Best” must mean proven
quality/cost tradeoffs on published workloads, not the fewest chunks or a single
throughput number.

## 4. The big transition: 2.0.0

**Status: implemented; included in the next 2.1.0 release.** Public API and persisted
representation changes are documented in the migration guide.
Reuse existing parsers, `TextIndex`, engines and utilities behind a shared
finalization pipeline. A Rust rewrite, hosted product, OCR engine, vector database
client stack and new embedding algorithms are outside this milestone.

### 2.0-A — Freeze contracts and establish evidence

Dependencies: none. Owns F05/F10 and baseline regressions for all other findings.

- [x] Add failing regression cases for F01–F09 before the corresponding fixes.
- [x] Inventory supported public symbols, actually supported options and parser
      capabilities; distinguish stable core from experimental integrations.
- [x] Establish one source for package/runtime version and verify the existing
      1.0 tag/changelog relationship without changing published tags.
- [x] Measure all Python source in coverage; separate optional-integration reports
      without hiding engines. Move a bounded invariant suite into normal CI.
- [x] Freeze a small, licensed corpus with UTF-8, Turkish/CJK, malformed code,
      mixed Markdown, tables and incremental edits; store expected invariants.
- [x] Decide dependency layout: minimal text core, optional `code` grammars,
      `semantic` NumPy/model helpers and specific integrations. Moving currently
      mandatory dependencies is a documented 2.0 installation change.

Acceptance: each advertised option has a validation/behavior test; actual
coverage, installed dependency sets and current failing contract cases are known.

### 2.0-B — Source, chunk and schema contracts

Dependencies: 2.0-A. Owns F06/F08 and the shared representation.

- [x] Introduce a document/source descriptor with canonical UTF-8 text, logical
      source ID, revision and loader metadata. Record normalization/encoding.
- [x] Define byte ranges as zero-based half-open UTF-8 ranges. Define line ranges
      explicitly, including trailing newline and empty-input behavior.
- [x] Separate source text, structural context and generated enrichment. A raw
      chunk is always an exact slice of its declared canonical source; PDF bytes
      or notebook JSON are not confused with extracted text.
- [x] Preserve page/cell/element references; rebase entities, scopes and diagnostics
      together. Never invent original-byte coordinates where extraction lost them.
- [x] Add explicit `lossless` and retrieval-oriented coverage policies. Lossless
      partitions include all source bytes; retrieval mode may omit trivia but
      reports skipped spans. With overlap, evaluate the union of source spans.
- [x] Version JSON/JSONL and store schemas; round-trip every documented field.
      Convert legacy records through a tested reader with a schema marker.

Acceptance: Unicode and multiformat conformance cases pass; source-slice fidelity,
nested range validity and serialization equality hold for every documented mode.

### 2.0-C — One configuration and budget pipeline

Dependencies: 2.0-B. Owns F04/F05 and engine consistency.

Target flow (conceptual names, not a promised import API):

```text
load source → parse structure → propose boundaries → pack spans
            → render context → validate exact budget → emit/export
```

- [x] Validate immutable user configuration; reject unknown options and invalid
      combinations. Keep internal precomputed indices out of public configuration.
      Implement each retained option or remove/reject it with a migration note;
      currently unused options must not survive as silent no-ops until a later minor.
- [x] Define typed loader/parser/sizer/boundary/context/export contracts. An engine
      supplies structure and candidate spans; common code enforces final contracts.
- [x] Require an explicit tokenizer/counter for exact token mode. Expose estimates
      under a distinct policy with provider identity and accuracy metadata.
- [x] Count the final embedding payload, including context, headers and overlap.
      Report raw-text and rendered-text counts separately.
- [x] Define overflow policy: strict split or error when a unit cannot fit;
      explicit structural overflow may preserve the unit but must report why and
      by how much. Strict mode never silently exceeds its budget.
- [x] Make overlap units and behavior consistent across engines and execution
      modes; reject unsupported combinations instead of silently ignoring them.

Acceptance: zero unreported budget violations on conformance corpus; sync and
iterator results agree for equivalent supported options (apart from total-count
availability); token/provider failures produce actionable errors.

### 2.0-D — Trustworthy identity and incremental storage

Dependencies: 2.0-B/C. Owns F01/F02/F03/F07. These fixes cannot wait for a 2.x
feature release because existing indexing can otherwise retain stale vectors.

- [x] Separate logical document ID, content fingerprint, chunk occurrence identity
      and rendered embedding fingerprint. Include algorithm/config/tokenizer and
      context changes in invalidation; content hashes alone cannot identify repeated
      equal chunks or a definition whose external imports changed.
- [x] Preserve IDs across unaffected local edits where matching is unambiguous;
      define deterministic handling of duplicates, moved blocks and renamed files.
      Report updates/additions/removals explicitly, with compatibility conversion.
- [x] Scope stores to named collections and source roots. A partial scan must not
      delete unrelated data; deletion requires a completed scan of its owned scope.
- [x] Commit document revision, chunks and sync status atomically. Preserve last
      good state on parse/provider failure; retries must retry failed revisions.
- [x] Return chunks in document/range order. Namespace embedding caches by provider,
      model revision, preprocessing and dimensions; isolate concurrent use.

Acceptance: same-length edits, prefix insertion, duplicate content, config changes,
multi-root sync, interrupted writes and provider changes all pass regressions.

### 2.0-E — Execution boundaries and release migration

Dependencies: 2.0-C/D. Owns F09/F11 and release delivery.

- [x] Distinguish incremental output from file streaming. AST/document processing
      may retain O(source + structure); exporting adds only a bounded batch. Publish
      per-engine memory/first-chunk behavior instead of claiming universal O(1).
- [x] Bound async queues and in-flight work; implement cancellation and cleanup.
      Never collect the entire corpus before yielding a batch.
- [x] Keep parser/formatter plugins scoped to an instance or explicit registry;
      define plugin capability, ordering and error contracts.
- [x] Rename/isolate legacy JSON-RPC and document migration from `serve --mcp`.
      Require allowed roots with resolved symlink checks, request-size/resource
      limits and loopback binding by default. Retained HTTP needs Origin/Host
      validation and an explicit authentication policy for non-loopback access.
      Test traversal, symlink escape, invalid origins and oversized requests.
      Keep actual MCP an optional later adapter.
- [x] Publish a 1.x → 2.0 migration guide with old/new option mapping, import paths,
      offset/whitespace/overlap changes, output schema and dependency extras.
- [x] For stored/vector data: back up, build a separate v2 index, compare results,
      switch the consumer only after validation, and retain rollback to the old
      index. Regenerate embeddings whose payload fingerprint changed.
- [x] Keep documented legacy readers/aliases through 2.x with deprecation notices;
      do not emulate unsafe old diff/cache semantics. Do not mutate old stores in place.

Acceptance: core examples, CLI, file/batch/async, store round-trip and adapter
smokes run from built wheels, including a minimal-dependency environment.

### Release sequence and stable release gate

The original sequence below explains the dependency order. The maintainer chose
to deliver A–E and the 2.1 code milestone together as **2.1.0**, so creating each
intermediate prerelease tag is optional. The stable gates still apply.

Execute **A → B → C → D → E**. Regression/corpus work can run alongside B–D;
documentation and adapters follow the contracts rather than freezing them early.

- **2.0.0a1:** A/B contracts and schema prototype, explicitly experimental.
- **2.0.0a2:** C/D budget and incremental correctness integrated; migration fixtures.
- **2.0.0b1:** E complete, feature freeze, documented API/schema freeze.
- **2.0.0rc1:** wheel/sdist installation, migration rehearsal and benchmark review.
- **2.0.0:** release only after every gate below passes; tag, metadata and runtime
  agree, with changelog and artifact validation. Publish is a separate release action.

Stable release gates:

1. No open P0/P1 findings above; regressions fail before their fixes and pass after.
2. All documented source/budget/schema/invalidation invariants pass. Normal CI runs
   bounded property tests; extended fuzz/large-corpus jobs run before an RC.
3. At least **90% aggregate line+branch coverage** across Python source, with no
   entire core modules omitted; changed invariant logic has direct behavior tests.
   Measure optional integrations in dedicated jobs and report skips separately.
4. Ruff lint and format, strict mypy, rule sync and strict MkDocs build pass under
   a consistent documented tooling version. Supported Python versions pass CI;
   Linux/macOS/Windows have wheel install and basic functional smoke coverage.
5. All comparisons use the same tokenizer, effective budgets, overlap and corpus;
   raw results and failures accompany the report. A missing baseline is an explicit
   unestablished gate, never a release-quality pass. The first 2.x release uses the
   explicitly bound transition manifest above because the old reference violates
   the requested budget; subsequent releases use the valid prior-release gate.
6. On controlled runners, investigate >10% warm-throughput regression or >15% peak
   RSS growth versus the fixed baseline. Any accepted tradeoff records its reason
   and retrieval/correctness benefit. These are proposed thresholds, not results.
7. Two representative indexing examples complete v1 → v2 rebuild and rollback;
   verify stale-vector removal, source citations and full metadata retention.

For a single active maintainer, deliver one workstream at a time and split fixes
into reviewable PRs. Re-estimate after 2.0-A establishes test and compatibility
costs; no calendar date is promised before that evidence exists. If scope grows,
defer additive features below, not the correctness gates.

## 5. From 2.0 to 3.0: additive, bounded releases

**2.1 is implemented in the current working tree; 2.2 onward is planned.** Rows
are ordered by dependency rather than date. Each release
inherits the 2.0 gates, has one main theme and preserves the 2.0 source/schema/API
contract. Experimental additions are opt-in and named as such. Patch releases
contain compatible fixes; no core rewrite belongs in a 2.x minor.

API compatibility does not mean identical boundaries across all future bug fixes.
Version algorithm/preset identifiers and record grammar/tokenizer revisions in the
configuration fingerprint. Maintain golden outputs for fixed versions; release
notes must call out boundary changes and their reindexing/embedding implications.
An intentional new strategy or default requires an opt-in preset or major migration.

| Release | Scope and existing work to extend | Dependency | Acceptance / explicit limit |
| --- | --- | --- | --- |
| **2.1.0 — Code quality (implemented)** | Language capability matrix; decorators, comments, generics, nested scopes and mixed fences; parser fallback diagnostics and entity range sweep | 2.0 source and parser contracts | Source/code fixtures verify boundaries and rebased entity ranges; capability output distinguishes availability from tested extraction. No additional language is advertised solely from an enum entry |
| **2.2.0 — Prose and tables** | Multilingual sentence boundaries (including Turkish/CJK), Markdown lists/tables/footnotes, RST and LaTeX refinements | 2.0 shared sizing/context | Table row/header relationships and multilingual spans pass fixtures; contextual header repetition stays within budget; no built-in OCR |
| **2.3.0 — Document adapters** | Optional Docling adapter; PDF/DOCX page/element provenance and notebook cell/output handling using existing loaders | 2.0 provenance, 2.2 document structure | Citation round-trips and missing-extraction diagnostics pass; report extraction and chunking costs separately; no invented original offsets |
| **2.4.0 — Retrieval integration** | Strengthen existing hierarchy; sentence-window expansion; native LangChain splitter and LlamaIndex node parser preserving IDs, context and relationships; optional MCP adapter as an independent follow-on | 2.0 identity/schema/security, 2.1/2.2 structures | Small-node retrieval → parent context works within fixed budgets; framework contract tests use pinned supported versions. MCP ships only after lifecycle/tools/transport tests pass, in any later minor if needed |
| **2.5.0 — Incremental operations** | Extend already-correct store/diff with resumable corpus jobs, checkpoints, duplicate/move diagnostics, collection maintenance and dry-run change plans | 2.0-D/E mandatory safety | Interrupted multi-file runs resume without losing last good data; measure re-embedded fraction after local edits; do not postpone basic data-loss fixes here |
| **2.6.0 — Semantic control** | Extend the already validated adaptive-threshold/cache baseline with opt-in controls, boundary explanations, provider cost accounting and multilingual semantic evaluation | 2.0 provider/budget contract, 2.2 corpus | New controls have behavior tests; report retrieval gain and embedding cost against structural baseline; existing no-op options were resolved in 2.0, not postponed here |
| **2.7.0 — Evaluation and presets** | Source-span recall/precision/IoU; retrieval Recall@k/nDCG/MRR; evidence-backed code/prose/mixed presets and reproducible tuning CLI | 2.0 baseline, 2.4 retrieval examples | Presets include corpus/model/tokenizer versions and held-out scores; byte-union coverage catches missing suffixes; no global “quality” score without interpretation |
| **2.8.0 — Performance** | Profile Python scans/copies and bounded-memory execution; improve existing optional Rust kernels only where measured | 2.0 execution contracts, 2.5 workload, 2.7 measurements | Publish p50/p95/RSS/first-chunk metrics and Python/Rust result parity; acceleration stays optional. Independent plugin/MCP integrations cannot block this release |
| **2.9.0 — 3.0 preparation** | Freeze stable extension contracts; complete compatibility/deprecation inventory, migration tooling, documentation and integration matrix | 2.1–2.8 gates | Every proposed removal has a replacement, warning and migration example; zero new foundations added during stabilization |
| **3.0.0 — Compatibility checkpoint** | Remove only pre-announced legacy aliases/readers/options retained from 1.x; promote proven extension APIs | 2.9 migration rehearsal | Same 2.0 core representation and defaults for supported APIs; one focused migration, no second architecture rewrite |

**3.0 rule:** removal requires at least two minor releases of notice and a migration
path. Legacy data must remain recoverable through a versioned offline converter.
If no breaking removal is justified, continue 2.x until one is; a round version
number alone is not a technical reason to break compatibility.

### What “best” will be measured against

- **Correctness:** canonical-source slice equality, span union coverage, valid
  UTF-8, correct nested coordinates, deterministic metadata, exact budget results.
- **Retrieval:** Recall@k, nDCG@10, MRR and source-token precision/recall/IoU;
  additionally recall at a fixed retrieved-token budget, since chunk sizes differ.
- **Structure:** declaration/decorator attachment, heading attribution, table
  preservation, parent containment and usable source citations.
- **Incremental cost:** unchanged-content ID retention, embedding invalidation
  accuracy, re-embedded fraction per edit, deletion accuracy and recovery behavior.
- **Performance:** cold/warm cost, p50/p95 latency, bytes/tokens per second, peak
  RSS, time to first chunk, dependency footprint and embedding/API calls.

Freeze source revisions, licensed datasets and query evidence spans. Keep tuning
and held-out data separate. Fix embedding model/tokenizer/retriever across chunker
comparisons; record actual output budgets rather than only requested sizes. Run
both code and prose baselines; separate extraction, parsing, chunking, enrichment
and embedding costs. Publish environment, seeds, dependency versions and failures.
Chroma's [token-level evaluation](https://www.trychroma.com/research/evaluating-chunking)
is a useful methodology reference, not a substitute for Omnichunk measurements.

## 6. From 3.0 to 4.0: longer-term vision

These are **research directions**, not stable API or date commitments. Keep the
2.0 text contract useful throughout 3.x. Promote an experiment only after it
demonstrates retrieval value at an acceptable cost on held-out tasks.

| Horizon | Experiment | Evidence needed before promotion |
| --- | --- | --- |
| **3.1.x** | Optional late chunking integration: contextual token embeddings pooled over established source spans | Correct tokenizer/span alignment, long-context window behavior, memory/cost and recall comparisons; existing sentence-vector callbacks alone cannot implement this |
| **3.2.x** | Generated contextual enrichment and proposition-linked evidence, using user-owned models | Preserve raw source separately; record model/prompt/revision, cache outputs and charge their tokens; measure gains against deterministic imports/headings |
| **3.3.x** | Query-adaptive context assembly over hierarchy/entity/source graphs; selective context expansion | Budgeted retrieval improvement with valid citations and bounded graph traversal; chunking remains independently usable |
| **3.4.x and later** | Incremental cross-repository relationships, multimodal adapters for pages/regions and time-aligned transcripts; learned boundary policies as experiments | Explicit permissions/source ownership, region/time provenance, drift evaluation and reproducible deterministic fallback; reuse external extraction/model systems |
| **4.0.0 decision** | A richer source-region/context-plan representation only if validated multimodal or query-adaptive work cannot fit existing extension points | Written compatibility case, real adopters, conversion/rebuild/rollback tooling and published quality/cost evidence; retain the text-only path |

[Late chunking research](https://arxiv.org/abs/2409.04701) contextualizes token
representations before pooling; it is distinct from embedding sentences to select
boundaries. [Contextual retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
adds generated chunk-specific explanations before indexing; it is distinct from
the current deterministic heading/import context. Neither is assumed to improve
every workload, and neither introduces mandatory external API calls into core.

Do not turn the library into a hosted vector database, a universal ETL platform,
an OCR product or an autonomous model-calling service. Add integrations at the
edges while preserving a small, local, testable chunking library.

## 7. Documentation and roadmap maintenance

- `README.md`: current features, working entry points and material limitations.
- `ARCHITECTURE.md`: actual implementation and coordinate/execution behavior.
- `ROADMAP.md`: this audit, priorities, release gates and future direction.
- `CHANGELOG.md`: implemented changes and verified release history; future work
  stays here in the roadmap rather than appearing as completed changelog entries.
- `docs/migrations/index.md`: consolidated historical notes; `docs/migrations/v2.md`
  documents implemented APIs and executable rebuild/rollback examples.
- `CONTRIBUTING.md`: contribution, maintainer, governance and release process.
- `benchmarks/README.md`: reproducible commands and interpretation, not stale
  machine-specific leaderboards or completed-task reports.

This cleanup merges governance/maintainer notes and three historical migration
pages; retires the duplicate 0.10.1 announcement and two old benchmark reports.
Git retains historical content. Security/community policies, example instructions,
fixture Markdown and the CI-required synchronized AI rule files remain.

At each release, update status with PR/test/report evidence, revisit the next two
milestones and publish migration changes. A checkbox is complete only when its
acceptance behavior exists and has been verified.
