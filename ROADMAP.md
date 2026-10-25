# OmniChunk roadmap

**Reviewed: 2026-10-24. Baseline: `7741440`, package version `2.1.4`.**
This is a delivery plan, not a declaration of enterprise readiness or a claim
about the currently published PyPI version. Implementation belongs in the
[changelog](CHANGELOG.md); guarantees belong in the
[contract reference](docs/reference/contracts.md). Historical audit transcripts
and superseded release plans remain in Git history.

## Vision: the trusted boundary between documents and retrieval

Make OmniChunk the default choice when an engineer asks: **“How do I turn this
changing corpus into useful, attributable, affordable RAG context?”**

Make five outcomes routine: useful retrieval, exact source citations, predictable
model budgets, safe index updates and easy integration. The distinctive
opportunity is code and mixed-document corpora: preserve program and document
structure while keeping the index correct after edits, extraction, enrichment,
serialization and export.

Start with three complete user journeys:

| User problem | Outcome to deliver | Evidence of success |
| --- | --- | --- |
| A code assistant retrieves a function without the imports, class or explanation needed to use it | Structure-aware code plus adjacent documentation, with navigable citations | Better held-out code retrieval at the same context budget; valid source references |
| A knowledge assistant loses table headers, section context or page references | Document elements and context survive chunking and framework conversion | Correct answer-evidence retrieval on manuals, policies and multilingual documents |
| A changing corpus accumulates stale vectors or re-embeds everything | Explainable updates with explicit additions, deletions and embedding reuse | Interrupted/replayed updates converge to a clean rebuild; measured embedding savings |

Keep the core local, deterministic where inputs/providers are deterministic,
typed and free of mandatory third-party dependencies. Optional integrations bring
extraction, embedding models and database clients. Applications own authentication,
authorization and orchestration.

## Where the project stands

The foundation already includes structural code/prose/markup engines, diagnosed
parser fallbacks, canonical UTF-8 ranges, final-payload budget checks,
lossless/retrieval policies, versioned serialization, hierarchy, scoped SQLite
storage, diffs, semantic utilities, async output and exports. MkDocs builds a real
API/user documentation site and should remain.

The foundation audit found defects in important existing flows.
[PR #27](https://github.com/oguzhankir/omnichunk/pull/27) addressed them:

| Finding | Required behavior | Implementation area |
| --- | --- | --- |
| `batch()` drops per-input options accepted by `abatch()` | Source identity, sizing and tokenizer overrides agree across entry points | `chunker.py`, batch regressions |
| Delimiter-free input degenerates into tiny chunks; AST hard splitting can cut UTF-8 codepoints | Useful progress, exact source slices, valid Unicode and enforced budgets | Finalization/window splitting regressions |
| Token-budget selection counts raw text instead of the rendered retrieval payload | Selection accounts for context/overlap; unknown rendered token counts fail explicitly | `budget/optimizer.py`, budget regressions |
| Framework conversions omit native IDs; Weaviate requires UUID-shaped IDs | Deterministic native IDs, preserved logical IDs and a defined deletion mapping | `serialization.py`, export regressions |
| Vector exporters accept malformed embeddings | Reject empty/ragged/non-finite vectors and dimensions changing across a stream before yielding the affected batch | Vector/stream export regressions |
| Unknown empty SQLite schemas can be treated as usable stores | Reject incompatible databases without modifying their schema | `store/chunk_store.py`, persistence regressions |
| RPC input handling permits non-finite numbers and unsafe file types | Reject invalid numeric limits and nonregular files; encode response IDs safely | `mcp/server.py`, RPC regressions |
| Examples and duplicated AI instructions drift from the API | Executable examples, one `AGENTS.md`, working docs checks and no duplicate architecture/audit documents | Examples, docs and CI configuration |

The PR and CI results are the verification record. This document does not preserve
old machine-specific test counts as evidence for today's code.

Remaining gaps are product work, not reasons to call existing utilities absent:

| Gap | Evidence in the current implementation | Priority / milestone |
| --- | --- | --- |
| Retrieval quality needs independent evidence | A synthetic labeled corpus and lexical retrieval runner now measure quality; external validation and frozen dense-model comparisons remain open | P0 / M1 |
| Production operating limits need measurement | The acknowledged journal and Qdrant/pgvector sinks now have crash/replay and real integration tests; large deployments, throughput limits and hosted failover remain to characterize | P1 / M4 |
| Rich extraction metadata still needs adapters | Native framework/journal records preserve caller metadata and canonical chunk snapshots; original page/element geometry still depends on richer extraction | P1 / M3 |
| Rich document structure is flattened | `LoadedDocument` holds canonical text/segments; PDF/DOCX loaders provide text extraction, not OCR or full page/element geometry | P1 / M3 |
| Sentence segmentation is still heuristic | Unicode starters, CJK terminators and CRLF paragraphs are supported; abbreviations, language-specific ambiguity and wider RTL coverage still need validation | P1 / M3 |
| Streaming does not bound total source memory | Iterators retain source/AST state; semantic/structured workflows retain per-document work | P1 / M4 |
| Enterprise operating limits are not characterized | Existing tracing and release checks do not establish corpus-scale RSS, crash recovery, resource limits or long-term support | P1 / M4 |
| RPC remains experimental | Custom JSON-RPC is not MCP; serving lacks bounded isolated execution and hard work deadlines | P1 / M4, optional service |
| Advanced retrieval methods are incomplete | Hierarchy/graph/proposition utilities exist; late token pooling, sentence-window retrieval and evaluated generated context are not complete workflows | P2 / M5 |

P0 blocks a trust/quality claim; P1 blocks the corresponding production use case;
P2 needs evidence before promotion. New source-integrity/security defects take
precedence over feature work.

## Learn from the strongest alternatives

Primary documentation inspected on **2026-10-24**. These are documented
capabilities and opportunities, not a performance ranking or claims that
competitors lack correctness. Pin released versions for comparisons; documentation
alone does not prove equivalent behavior.

| Alternative and primary source | Established strength | OmniChunk response |
| --- | --- | --- |
| [Chonkie chunkers](https://docs.chonkie.ai/oss/chunkers/overview) and [pipelines](https://docs.chonkie.ai/oss/pipelines) | Common APIs across structural, semantic, table, late and neural strategies; composable workflows | Make the common path easy to compose; add row/header-aware tables in M3; evaluate late/neural methods in M5 |
| [LangChain splitters](https://docs.langchain.com/oss/python/integrations/splitters/index) and [indexing](https://reference.langchain.com/python/langchain-core/indexing/api/aindex) | Familiar splitter interfaces and indexing with record tracking and incremental/full/scoped cleanup | Native adapter, explicit source ownership and tested cleanup/retry recipes in M2 |
| [LlamaIndex node parsers](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/) and [ingestion](https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/) | Hierarchical/sentence-window nodes, cached transformations and document-hash-based updates | Preserve native node relationships; integrate cached ingestion and evaluate small-to-big retrieval in M2/M5 |
| [Docling chunking](https://docling-project.github.io/docling/concepts/chunking/) | Token-aware refinement of document elements, contextualization and repeated table headers | Accept structured extraction output; retain page/element references and budget rendered context in M3 |
| [Unstructured chunking](https://docs.unstructured.io/open-source/core-functionality/chunking) | Section/page-aware element grouping, isolated tables and access to original elements | Preserve element lineage and document boundaries through chunking/export in M3 |
| [semchunk](https://github.com/isaacus-dev/semchunk) | Small tokenizer/counter API, offsets, overlap and multiprocessing | Offer a simple preset path; compare equivalent counters and actual payload budgets in M1/M4 |
| [text-splitter / semantic-text-splitter](https://github.com/benbrandt/text-splitter) | Rust/Python structural splitting with character/token sizing | Profile before adding native code; prove Python/Rust parity and workload-specific speed in M4 |

Algorithm count is not the success metric. Pursue the best demonstrated
quality/cost tradeoff for the three user journeys, with fewer integration and
operational surprises.

## Delivery sequence

Milestones are ordered gates, not promised dates or automatic version bumps.
Maintain one main milestone and at most one independent integration/documentation
track. Each milestone can ship across compatible releases; completion requires
linked tests, reports and migration evidence.

### M0 — Repair and simplify the current product

**Status:** implemented and merged in [PR #27](https://github.com/oguzhankir/omnichunk/pull/27);
publication remains subject to the release gates.
**Dependency:** none.

- Fix the batch, splitting, budgeting, export, store and RPC defects above with
  reproducible regressions.
- Keep API/user/migration documentation; remove redundant AI rule copies, their
  synchronization machinery and `ARCHITECTURE.md`.
- Provide an offline chunk → retrieve → cite → update → delete example with
  assertions and explicit boundaries around external writes.
- Require lint, formatting, strict typing, configured coverage, strict docs build,
  example execution and wheel/sdist validation before release.

**Exit:** regressions pass, documented commands work in a clean environment, and
the PR identifies untested optional backends and hosted CI outcomes. M0 repairs
the foundation; enterprise readiness still requires M1–M4.

### M1 — Prove retrieval value and make tuning reproducible

**Status:** in progress. **Dependency:** M0. **Owner role:** evaluation/core maintainer.

The first delivery adds a versioned, original synthetic corpus with 300
evidence-labeled queries, document-disjoint development/test splits, ranking and
source-evidence metrics, equivalent-budget adapters and an offline tuning/report
runner. See [benchmark commands](benchmarks/README.md#retrieval-evaluation-and-tuning).
Its fixed lexical retriever and authored labels provide a reproducible baseline;
independently validated corpora, frozen dense-model comparisons and production
design-partner evidence remain open before this milestone can be completed.

The next delivery repairs boundary defects exposed by the development report:
preserve fitting paragraphs/table rows, use Unicode sentence boundaries and count
complete contiguous payloads when grouping prose. Keep the corpus and retrieval
configuration fixed, report per-language/document wins and regressions, and only
evaluate held-out documents after the implementation is frozen. Follow with
configured-unit AST window sizing for multibyte code; this repair now measures
complete source ranges during grouping and splitting, including nonadditive token
costs. Independent corpus and dense-model validation remain the M1 completion gate.

- Publish a licensed, versioned corpus with code, Markdown/manuals, tables and
  mixed documents. Start with **300 evidence-labeled queries** across the user
  journeys, including English, Turkish and a no-whitespace script. Separate tuning
  and held-out documents; disclose synthetic query generation.
- Implement Recall@k, nDCG@10, MRR and source-span precision/recall/IoU. Compare
  recall at fixed retrieved-token budgets as well. Keep structural coverage and
  heuristic coherence distinct from retrieval quality.
- Compare appropriate Chonkie, LangChain, LlamaIndex, semchunk and text-splitter
  configurations. Use the same extracted elements for Docling/Unstructured chunking
  comparisons; measure extraction differences separately.
- Freeze tokenizer, embedding model/revision, retriever, overlap and context policy.
  Report actual payload sizes, variance, latency, RSS, embedding calls, chunk counts
  and re-index cost. Publish raw reports, environment and failures.
- Add a local tuning/report command with explainable code/prose/mixed presets;
  never silently change the strategy or call a model.

**Exit:** a reproducible held-out report, validated equivalent-budget adapters and
guidance showing wins *and* losses. A leadership claim needs a repeatable advantage
over the strongest evaluated baseline at comparable cost; a tie/loss prompts
investigation. [Chroma's token-level evaluation](https://www.trychroma.com/research/evaluating-chunking)
is a methodology reference, not evidence about OmniChunk.

### M2 — Make indexing and framework adoption dependable

**Status:** implemented; PR verification and release publication are separate gates.
**Dependency:** M0; use M1 for retrieval decisions.
**Owner role:** integration/indexing maintainer.

Delivery includes `IndexJournal`/`IndexPlan`, persistent prepared vectors,
acknowledged Qdrant/pgvector sinks, native LangChain/LlamaIndex adapters, preserved
metadata and a proper Pinecone request envelope. Independent process-crash and
competing-worker tests cover replay and stale-write prevention. Minimum/current
framework/SDK tests exercise real Qdrant local mode and PostgreSQL 16 with
pgvector. The [indexing guide](docs/indexing.md) documents executable recipes,
source/scope ownership, migration, rollback and at-least-once semantics.

The journal uses a separate database from `ChunkStore` and serializes writers
while external batches run. Batch bounds do not establish total-memory bounds,
and acknowledged delivery does not provide atomic multi-batch reader visibility.
These limits remain explicit inputs to M4; no distributed exactly-once or
application authorization guarantee is implied.

- Ship optional native LangChain splitter and LlamaIndex node/transform adapters.
  Preserve IDs, source references, metadata and hierarchy without accidental double
  splitting or embedding context twice. Define explicit metadata propagation,
  including caller-owned ACL/source attributes and vendor type/size constraints.
- Separate vendor request envelopes from individual records; validate actual SDK
  calls and document ID/schema migrations before changing existing export shapes.
- Define a serializable **index change plan**: collection/source/revision,
  additions, removals, metadata-only changes, embedding invalidations and hashes of
  the exact payload plus model/preprocessing revision. Include a dry-run view.
- Add an optional acknowledged sink protocol with idempotency keys, bounded batches,
  retry classification, a durable pending-work log and checkpoints. Keep local
  cache commits separate from remote acknowledgement; do not promise distributed
  exactly-once writes. Resume and reconcile after failed batches/process restarts.
- Define scoped scans, explicit deletion and stale-generation cleanup. Preserve
  namespace ownership through adapters. Demonstrate downstream ACL enforcement in
  application recipes; metadata storage alone provides no tenant authorization.
- Maintain runnable local retrieval, Qdrant and pgvector recipes first. Add vendor
  integrations when a maintainer and version-matrix tests exist.

**Exit:** replayed plans and injected crashes converge to a clean rebuild with
zero stale/deleted records; unchanged payload/model fingerprints reuse embeddings;
failed writes remain pending. Test native adapters against declared minimum/current
compatible versions. Cross-collection deletion and metadata propagation tests pass.

### M3 — Win on real documents, languages and source fidelity

**Status:** planned. **Dependency:** M1 corpus; coordinate metadata with M2.
**Owner role:** document/parser maintainer.

- Add optional Docling and Unstructured element adapters instead of an OCR engine.
  Preserve extraction revision, page/element IDs and available region coordinates
  alongside canonical text spans; never describe those as original binary offsets.
- Add table row/cell structure, repeated headers as derived context, captions,
  lists and section policies. Test oversized rows, empty cells, nested markup and
  multi-page tables with exact rendered-token accounting.
- Make sentence boundaries pluggable with Unicode/language-aware defaults. Expand
  Turkish/CJK/Arabic/RTL, abbreviations, combining marks, emoji and mixed code/prose
  cases. Preserve bytes when linguistic heuristics are uncertain.
- Expand grammar/extraction fixtures based on demand; publish capability levels for
  detection, parsing, entities and context. Diagnose every fallback.

**Exit:** page/element citations survive JSON/framework round-trips; conformance
fixtures satisfy source/budget policies; M1 reports retrieval/boundary results per
language/document slice instead of hiding regressions behind an average.

### M4 — Establish an enterprise operating contract

**Status:** planned. **Dependency:** M1 measurements and M2 recovery semantics.
**Owner role:** runtime/release maintainer.

- Profile 1 MiB, 10 MiB and 100 MiB documents plus a 100,000-file corpus on a declared
  runner. Measure p50/p95 latency, peak RSS, first-chunk time, queue depth and
  cancellation latency; separate parse, split, enrich and embed cost.
- Bound task submission/results; offer checkpointed directory processing and a
  file-like/incremental path where parsing permits. State per-format memory
  complexity and unavoidable full-document work.
- Add configurable source-size, nesting and work limits; fuzz malformed parsers
  and structured archives; document thread/process safety and callback cancellation.
  Retain optional Rust kernels only where measured gains justify maintenance.
- Publish content-safe telemetry for fallback, overflow, cache hits, stage timings
  and error categories. Do not expose raw text or sensitive paths by default,
  including through callback exceptions.
- Maintain dependency constraints, vulnerability triage, release provenance/SBOM,
  supported Python/OS tests and deprecation rules. Stabilize extension points after
  at least two independent integrations exercise them.
- Keep serving experimental until file/count/response/work limits, isolated parser
  execution and an explicit filesystem threat model are tested. Resolved paths do
  not secure a filesystem being modified by an adversary. Add standard MCP only
  as an optional conformant integration with lifecycle/tool conformance tests.

**Exit:** published workload limits, bounded-growth evidence and recovery tests;
no unexplained regression beyond the existing same-runner performance threshold;
Python/Rust output parity; tested offline install and rollback. Publish security
response/support expectations the maintainers can sustain. No uptime SLA or
compliance certification is implied by a library release.

### M5 — Earn advanced capabilities through experiments

**Status:** research backlog. **Dependency:** M1 evaluation; M2/M3 provenance.

| Experiment | Promotion gate |
| --- | --- |
| Sentence-window and parent/child context expansion | Better held-out recall at a fixed context budget; valid citations and bounded expansion |
| Late chunking with user-selected long-context models | Verified token/source alignment, window/pooling semantics and memory/quality cost; sentence embeddings alone are insufficient |
| Generated contextual retrieval and proposition-linked evidence | Original text stays separate; model/prompt/revision recorded; caching, cost caps and unsupported-claim evaluation |
| Neural/adaptive boundaries and domain presets | Beat the structural baseline on held-out tasks without hidden provider calls; deterministic fallback and reproducibility report |
| Graph-guided context and multimodal region/time adapters | Adopter demand, bounded traversal, preserved permissions/provenance and evidence that existing text extensions are insufficient |

[Late chunking](https://arxiv.org/abs/2409.04701) pools contextual token embeddings
after model processing; it is not a rename of the current semantic splitter.
Research stays optional and experimental until promotion gates pass. A Rust
rewrite, hosted vector database, universal ETL service and OCR stack are outside
this roadmap.

## Release, adoption and maintenance gates

An enterprise-ready release must pass **all** of these with published evidence:

| Gate | Required evidence |
| --- | --- |
| Correctness | Source/budget/serialization conformance, sync/async parity, malformed-input tests, zero known silent-loss or stale-index defects |
| Quality | Reproducible M1 held-out retrieval results and workload-specific selection guidance |
| Index lifecycle | M2 replay, failure, deletion, isolation and migration/rollback tests against real supported integrations |
| Operations | M4 measured limits, safe diagnostics, dependency/security policy and validated artifacts |
| Compatibility | Supported runtime/integration matrix; announced deprecations and tested data recovery |
| Usability | Clean-install quick start, executable recipes, searchable API docs and actionable fallback/budget troubleshooting |

Keep compatible improvements in 2.x. A breaking release needs a concrete contract
change, notice over at least two minor releases and migration/rebuild/rollback
recipes. A round version number is not a reason to redesign the system.

Adoption work accompanies delivery: recruit **three design partners** covering the
user journeys, turn their failures into fixtures, and publish a tested recipe and
evidence-based release note per milestone. Seek upstream adapter listings after
compatibility tests exist. Track time to first successful retrieval, integration
failures, production reuse and maintainer response time; stars/downloads are
secondary signals. These are targets, not claimed existing users.

Use `README.md` for the entry point, `docs/` for built user/API/migration guidance,
`examples/` for runnable recipes, `CHANGELOG.md` for shipped behavior, and this file
for future priorities. Keep `AGENTS.md` as the sole repository AI instruction file.
At each release, record evidence, nominate an accountable owner for the next slice
and reassess the next two milestones. New ideas enter the backlog; they do not
bypass correctness, retrieval evidence or maintainability.
