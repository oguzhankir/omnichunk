from pathlib import Path
import csv,json
W=Path('/workspace/work/omnichunk-v3');D=W/'drafts'
rows=list(csv.DictReader((D/'development-outcomes.csv').open()))
meta=json.loads((D/'development-inputs.json').read_text())
def selected(ending,tool):
 return sorted([r for r in rows if r['artifact'].endswith(ending) and r['tool']==tool],key=lambda r:int(r['capacity']))
def pair(ending,tool,field='recall',fmt='.6f'):
 r=selected(ending,tool)
 if len(r)!=2:return 'pending'
 return ' / '.join(format(float(a[field]),fmt) for a in r)
def trow(model,label,ending,tool):
 return f"| {model} | {label} | {pair(ending,tool)} | {pair(ending,tool,'precision')} | {pair(ending,tool,'vectors','.0f')} | {pair(ending,tool,'native_passage_tokens','.0f')} |"
lines=['''# Real-source retrieval quality, v3 — development record and validation draft

**Draft status: development results only. Sealed validation has not been released or read for this draft. Universal leadership is not established.** This record separates default correctness repairs from optional cost/quality profiles, retains negative experiments, and does not treat source retrieval as answer accuracy. Model-specific native tokenizers prevent interpreting the two encoders as a controlled model comparison.

The baseline is main `e63c7f097a8ccec39262c8fb00fb2375a3e5283d`. Final runtime behavior is currently frozen by the implementation at `7413977892e14e481e8aa4e99333f3a4c34b6299`; final review/test-only documentation commits, complete gate outcomes and the formal validation freeze remain **pending**. Historical trial commits are retained rather than overwritten. Validation conclusions, paired confidence intervals and final source/package/model fingerprints will be added after the freeze and once-only held-out runs.

## Outcome that can be claimed now

On the isolated-function development task, the corrected structural default improves mean recall in all four encoder/capacity cells versus prior main, with fewer vectors. Explicit code compaction improves those means further and exactly matches the simple fixed splitter in all four cells. That tie is an important limit: this task does not yet establish an advantage over a strong simple baseline. Stronger native CodeSplitter and real-file rival results are still pending, so no strongest-rival claim follows from the current table.

The Turkish compact prose profile improves some observed development means with fewer vectors, but the fixed splitter remains stronger on this development sample. Markdown packing lowers vector counts while harming synthetic development recall and therefore remains an explicit option. Rendering minimal source context adds index tokens and fails to beat the fixed raw splitter across the declared exploratory study; it is not selected as a default improvement.

## Protocol and separation from previous experiments

`protocol.json` was recorded before selection. Only development labels inform changes; previously observed SQuAD validation/test splits from older reports are not new held-out evidence. Original synthetic and original SQuAD development remain regression/development data. The fresh corpora and their limitations are below. A real-file code view was added by a separately declared protocol before its first score; its validation commitment was sealed first.

| Setting | Fixed policy |
| --- | --- |
| Native chunk limits | 64 and 96 model tokens, including native special tokens |
| Primary retrieved-context budget | Complete ranked prefix within 512 native tokens |
| Predeclared sensitivity budgets | 128 and 256 tokens; replay frozen rankings/vectors without new inference |
| Separate ranking cutoff | Top 5; ranking and byte evidence metrics are reported separately |
| Overlap / derived context | Zero overlap, no derived context in primary comparisons |
| Retrieval | Cosine over the complete candidate pool within the same split |
| Repeats and hardware scope | Three chunking repeats; CPU, two Torch threads and two interop threads; batch 32 |
| Input handling | Native full-input counting; reject encoder overflow, never silently truncate |
| Selection rule | Primary development evidence recall, precision and index work inspected; reject aggregate default domain recall decrease over 0.01, or retain only as explicit experimental profile |
| Claim gate | Positive source/repository-cluster paired recall interval against strongest admissible named rival, with index work disclosed; a mean win alone is exploratory |

Models are real pretrained local snapshots, not random weights: multilingual `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (384 dimensions, 128-token encoder limit), and English `sentence-transformers/all-MiniLM-L6-v2` at `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` (384 dimensions, 256-token limit). Both are previously verified Transformer + mean-pooling snapshots; the English snapshot additionally normalizes. English-model evidence is restricted to code queries in English. Model files and installed packages must be fingerprinted again for the final freeze.

Shared encoder preparation, frozen vector lookup/cosine ranking and chunking timings have separate scopes. Preparation deduplicates payloads across candidates, includes first model calls and is not a per-tool cold-start measurement. Vector/token counts quantify index work; frozen lookup timings are not end-to-end production retrieval latency. This study does not establish an enterprise latency or memory SLA.

## Data, rights and evidence contracts

| View | Development / validation | Source and license | Gold and scope |
| --- | --- | --- | --- |
| Turkish passage primary | 60 / 60 source passages; 120 / 120 questions | Belebele `7899cdfa4e1e0d733fd77c848e2c273cb1d32be2`, CC-BY-SA-4.0; original FLORES links retained | Complete originating Turkish passage, original question stem only; no answer choices indexed or queried |
| Isolated code primary | 64 / 64 functions and queries; 16 / 16 disjoint repositories | CodeSearchNet `bd0cf261e357a3eb5c8fba490d23ec1a1cd59555`; selected root MIT license verified at each function's exact commit | Original human documentation first paragraph queries, all AST docstrings removed from indexed functions; whole canonical function as evidence |
| Real-file code supplement | 37 / 35 files; 56 / 56 eligible existing queries; 15 / 16 repository clusters | Same selected CodeSearchNet questions and exact commits/MIT attributions | Complete original files and real neighbors, all AST docstrings removed; same functions mapped by original URL anchors + AST and rebased gold bytes |

**The two code views reuse the same queries and are correlated. They are not two independent datasets.** Real-file eligibility was declared before scores: original UTF-8 file at most 30,000 Unicode characters, valid Python 3 AST, and uniquely mapped selected function. Development excludes eight queries (seven size-limit, one Python 2 file); validation excludes eight (five size-limit, three Python 3 parse failures). All exact-commit source fetches succeed, and no function-anchor mappings fail among eligible files. Exact and whitespace/case-normalized complete query-substring audits after stripping AST docstrings find zero matches in either file split. Sole-body docstrings become `pass` to retain syntax; no synthetic file/function joins are used. Gold includes decorators, original indentation and the complete last body line, with coordinates into the transformed canonical text.

Belebele is human-authored reading comprehension with human translation, not original Turkish production traffic. Some question-only stems are underspecified without their omitted multiple-choice options. Whole-passage gold rewards recovering all source bytes, including sentences that may be unnecessary to answer. It is not independently audited minimal support. Likewise, human docstrings are code-search proxies rather than independently written user questions, and whole-function gold does not establish complete imports/dependencies or answer correctness. MIT-only Python, maximum source size and parse eligibility restrict the population. All public sources may occur in pretrained models' training data.

Turkish selection is namespace-SHA256 order over previously unseen eligible source links: first 120 links with two questions, alternating full passages into development/validation. There is zero normalized old-source/question overlap against both original Turkish and paired English passages/questions and all earlier published corpora; selected source links are distinct. Code selection uses the original CodeSearchNet validation/test repository-disjoint partitions, a deterministic namespace hash and exact-commit MIT verification. Neither selection uses embeddings or retrieval scores. Code sources and query summaries have zero cross-split normalized overlap. Use repository clusters for both code views and source-passage clusters for Turkish, not 64 or 56 supposedly independent function observations.

Initial full CodeSearchNet docstring queries exceeded the multilingual encoder limit on six development and seven validation questions. That run was rejected before valid scores; no silent truncation occurred. A pre-score amendment applies the exact original first-blank-line paragraph transform `full.split(chr(10) + chr(10))[0].strip()` to all selected queries. All selected functions remain; maxima become 98 development / 101 validation native tokens. Superseded manifests and commitments are retained. The Turkish upstream's 900 questions have maximum 38 tokens, selected development maximum 30, so none exceeds 128. An initial summary preflight used incorrectly escaped newline literals; its corrected audit is explicitly superseding, not independent evidence.

XQuAD Turkish was rejected as fresh evidence because all 48 source articles were already observed in older SQuAD corpora. Original TQuAD was not redistributed because its pinned original source tree contained no license declaration; a third-party mirror license was not assumed to grant rights. Corpus-specific provenance, original contributor links, importers and per-repository license texts accompany the data. The full code source is data and is never executed.

Validation custody is procedural within agent workspaces, not an independent external organization: source manifests and sealed archive hashes were committed, cleartext selection files removed, and keys held by custodian agents until the final source/model/settings freeze. Public upstream availability and shared filesystems limit this blindness claim. No validation quality result appears in this draft.

## Adapters and fairness

The baseline candidate set includes OmniChunk, the fixed counter-based splitter, semchunk, LangChain's generic recursive and native code strategies, semantic-text-splitter's text/Markdown strategy and native Python tree-sitter `CodeSplitter`, LlamaIndex's token and sentence strategies, and Chonkie's native sentence strategy. Each must pass source fidelity, complete native-budget and overlap conformance; all failures remain visible. Distinct strategies from one library are not independent libraries.

Recorded versions include semchunk 4.1.1, langchain-text-splitters 1.1.3, semantic-text-splitter 0.33.0, llama-index-core 0.14.25, chonkie 1.7.0, tree-sitter 0.26.0 and tree-sitter-python 0.25.0. Final environment fingerprinting and any revision-specific differences remain part of the freeze record. Chonkie's recursive count-only token contract remains unsupported; the sentence strategy is evaluated where it conforms. For example, its English real-file 64-token cell fails preflight and is retained as an error, while its valid 96-token cell is scheduled separately. No truncation, hidden splitter fallback or source-normalization repair is applied to make a rival appear conformant.

## Current isolated-code development snapshot

Values are **64 / 96** token capacities, at the primary 512-token retrieved budget. These are development means, not held-out results or confidence bounds. Native passage tokens include special tokens per payload. Historical compact prototypes remain in the complete CSV; only the final routing source belongs in the final-source rows below.

| Encoder | Profile | Evidence recall | Evidence precision | Vectors | Native passage tokens |
| --- | --- | --- | --- | --- | --- |''']
for model in ['multilingual','english']:
 for label,path,tool in [('Prior main','baseline-summary','omnichunk'),('Final structural default','final-routing-741','omnichunk'),('Final explicit compact code','final-routing-741','omnichunk-code-compact'),('Fixed baseline','baseline-summary','fixed')]:
  lines.append(trow(model,label,f'dev/code/{model}/{path}/report.json.gz',tool))
lines.append('''
The compact profile exactly ties fixed recall in these four cells. Default-versus-baseline differences do not imply a strongest-rival advantage; the pending CodeSplitter and real-file rows must be considered before selection or interpretation. Extra precision and index/workload outcomes for every tool are in `development-outcomes.csv`.

## Turkish development trials

All rows use multilingual MiniLM and 512 retrieved tokens. The equal-fragment and unconditional variants are separately recorded; a stronger single development mean is not used to claim significance. The selected behavior is an explicit `prose_boundary_policy="compact"`, while the default remains sentence-preserving.

| Trial | Recall, 64 / 96 | Vectors, 64 / 96 |
| --- | --- | --- |''')
for name,label,tool in [('baseline','Prior main','omnichunk'),('prose-fill','Fewer fragments only','omnichunk'),('prose-fill-equal','Allow equal fragments','omnichunk'),('prose-fill-unconditional','Unconditional measured candidate / explicit compact','omnichunk'),('baseline','Fixed baseline','fixed')]:
 p=f'dev/turkish/{name}/report.json.gz';lines.append(f'| {label} | {pair(p,tool)} | {pair(p,tool,"vectors",".0f")} |')
lines.append('''
## Every development trial and why it is retained or superseded

The complete machine-readable catalog includes all successful and failed cells from available primary reports, predeclared frozen sensitivity replays, the separate context study and lexical screens. It preserves each artifact hash, runtime, model, corpus fingerprint, capacity, budget, evidence metrics, vector count and available native-token workload. `development-inputs.json` fixes the exact snapshot; running jobs remain pending rather than omitted as losses or wins. Tables round means only for reading; raw artifacts and CSV retain full values.

| Trial / source | Investigation and disposition |
| --- | --- |
| Baseline / lexical mixed-block and packing screens | Initial counts and lexical TF-IDF diagnostics; lexical results are explicitly separate from pretrained dense evidence. Mixed Markdown block ownership repaired; no lexical score used as a dense-quality claim. |
| Comment sentence rebalance `e024911e` | Rebalances oversized documented statements at comment sentence boundaries. Original synthetic recall improves 0.936028 → 0.943129 at 64; 96 remains 0.950000. Source fidelity and syntax metadata preserved. |
| Comment isolation `e78e5a25` | Same observed recall, but 232 rather than 230 synthetic 64-token vectors; unnecessary isolation rejected in favor of rebalance. |
| Markdown pack `1671c36a` | Explicit paragraph packing: synthetic recall 0.919361 / 0.927778 versus baseline 0.936028 / 0.950000; vectors 219 / 157 versus 232 / 184. Rejected as default; optional packing remains for callers who evaluate its cost/quality tradeoff. |
| Combined repair `1b62380d` | Structural default synthetic recall 0.943129 / 0.950000, vectors 230 / 184. Combined packing still declines to 0.920435 / 0.927778 with 217 / 157 vectors. Both rows retained. |
| Prose fill `94b2aff6` | Fewer-fragment proposal reduces old SQuAD development vectors while recall ties; Turkish means and cost recorded above. Not silently promoted to default. |
| Equal-fragment prose `654cca49` | Turkish 64-token mean improves but 96 falls slightly; separate observed trial, not an independently confirmed win. |
| Unconditional measured prose `fca22407` | Becomes explicit compact policy. Original synthetic 64 recall declines 0.943129 → 0.941796; 96 ties. Caller-visible boundary tradeoff retained. |
| AST prefix carry `c8ebca2f` | Repairs unhelpful isolated declaration prefixes; code means improve in some cells and decline in others. Superseded by body-aware and scope-correct variants, with original outcomes retained. |
| Complete AST body packing `9e29254a` | Packs complete fitting body statements; original synthetic recall remains 0.943129 / 0.950000. Later source-scope repair takes precedence over picking this trial's best means. |
| Compact code `2b5d44ec` | Compares layouts for fewer fragments; English means 0.868277 / 0.896048. This historical prototype is not final-source evidence. |
| Reviewed compact code `23ac708d` | Budget/protected-definition correctness review; development passages/quality initially identical to compact prototype. Audit and superseding reason retained. |
| Fuller early compact payloads `0ecb5663` | Tie-breaker favors fuller earlier payloads. Code means improve, but original synthetic 96 recall falls from structural 0.950000 to 0.927778; explicit profile only. |
| Unsafe compact fallback / protection fixes | Prevents choosing pre-finalization overflow or layouts that split fitting definitions/documented groups; impossible protected-counter layouts now raise actionable `ChunkingError`. These are source/budget correctness requirements, not score-driven exceptions. |
| AST scope correction `7f44b2dd` / `be6d806` | Restricts pending-header carry to its own declaration body. Earlier favorable layouts cannot justify crossing source-scope boundaries. Fresh development input-equivalence/difference audits are retained. |
| Python data-string routing `7413977` | Detects actual AST docstrings rather than treating arbitrary triple-quoted data/SQL as prose. General routing correction changes one isolated source's layout; final-source reruns appear above. No query IDs or dataset paths are used in the runtime. |
| Minimal rendered context / original-path prefix study | Negative exploratory result described below; no default context promotion or hidden retrieval augmentation. |
| Stronger native rival adapter additions | Native LangChain code, LlamaIndex sentence, Chonkie sentence and semantic-text-splitter CodeSplitter make comparisons less dependent on generic text defaults. Conformance failures and stronger results remain visible; pending jobs cannot justify a leadership claim. |

Original dense screens for the five `v3-*` comment/prose labels are under the separately retained `external-quality-screen` artifact namespace, not the earlier v2 experiment's identically named report folders. Historical trial Git commits and input-equivalence records must accompany publication. The catalog does not collapse correctness revisions or correlated profiles into independent replications.

## Negative context study

A separate predeclared development protocol compares raw OmniChunk, minimal OmniChunk with the original source path, fixed raw chunks, and fixed raw chunks with a fitting source-path prefix. Both frozen encoders, capacities 64/96 and budgets 128/256/512 produce 48 cells. Derived context contributes encoder tokens but no additional raw-source evidence. All four profiles' payload/source alignment is independently audited.

Minimal OmniChunk increases index payload tokens by approximately 18%, improves some 512-budget means versus its raw baseline, and loses at every 128-budget cell. It still fails to beat the fixed raw splitter in all 12 model/capacity/budget recall cells. The experiment is retained as negative evidence, not removed because source-aware context sounded promising. The English fixed path-prefix 96-token/512-budget cell improves its own raw baseline; this does not validate OmniChunk's context mechanism. Full outcomes, source audits, preparation provenance and paired comparisons remain separate from primary no-context evidence.

| Encoder | Profile | Recall at 128, 64 / 96 | Recall at 512, 64 / 96 | Index payload tokens, 64 / 96 |
| --- | --- | --- | --- | --- |''')
context=json.loads((W/'context-dense-development/summary.json').read_text())
for model in ['multilingual','english']:
 for tool in ['omni-raw','omni-minimal-original-path','fixed-raw','fixed-original-path-prefix']:
  sets={b:sorted([x for x in context[f'{model}-{b}'] if x['tool']==tool],key=lambda x:x['chunk_capacity']) for b in [128,512]}
  p=lambda b,k,fmt:' / '.join(format(x[k] if k!='recall' else x['summary']['recall'],fmt) for x in sets[b])
  lines.append(f'| {model} | {tool} | {p(128,"recall",".6f")} | {p(512,"recall",".6f")} | {p(512,"payload_tokens","d")} |')
lines.append('''
## Public options and compatibility

Three independent opt-in controls are documented with a runnable recipe. Defaults remain `markdown_paragraph_policy="preserve"`, `prose_boundary_policy="sentence"`, `code_boundary_policy="structure"`. Markdown `"pack"` can combine fitting paragraphs only within compatible structural scopes. Prose `"compact"` can divide an otherwise fitting sentence during oversized fallback to obtain fuller payloads. Code `"compact"` can divide expressions in oversized declarations while protecting fitting definitions/documented root groups; it applies with `overflow_policy="split"` and rejects an infeasible protected layout rather than silently cutting it.

The profiles are not a promise to improve every corpus. They produce different payloads/configuration fingerprints and require index synchronization and embedding invalidation under the existing identity contracts. Numeric raw/derived-source ranges and final payload limits still apply. Source corrections such as proper AST scope and Python data-string routing can also change default output. Existing Markdown paragraph preservation and min-size preferences remain separate choices; caller options must be explicit and no model is invoked silently.

## Failed attempts, pending work and final validation requirements

The first full-docstring encoder attempt is preserved as a pre-score overflow failure. Earlier CLI-rejected invocations are retained and superseded by the supported runtime/corpus command; they are not successful quality cells. Chonkie sentence overflow is an admissibility error, not a zero recall score or hidden fallback. Source-size and Python syntax exclusions in the real-file view are counted, never repaired after seeing scores. Intermediate correctness tests and counter/source audits remain in the provenance record even when they force superseding a favorable trial.

**Pending:** final source-only equality across test/docs commits; final full test/lint/type/docs/package gates; completed real-file rival/default/compact development results; native CodeSplitter isolated/Turkish results; development-selected comparison references and formal freeze; final code/security reviews; validation release and once-only matrices; source/repository-cluster paired intervals and uncertainty; final raw-artifact and numerical audit. A pending row is not a supported win.

After the freeze, release the committed validation bytes once, preflight every declared adapter and keep each failure, run the no-overlap/no-context primary matrix with both declared capacities, and derive 128/256 sensitivity results from the exact frozen vectors/rankings. Keep all public profiles and strongest admissible references visible; do not select a new profile, rival, query or corpus after inspecting validation results. Validation conclusions must state mean wins, ties, losses, paired uncertainty and native index work together. No release, milestone completion or universal quality/throughput leadership follows from development results alone.
''')
lines.append(f'\nCatalog snapshot: {meta["recorded_utc"]}; {len(rows)} available cells from {len(meta["artifacts"])} exact input artifacts. `development-outcomes.csv` SHA256 `{meta["csv_sha256"]}`.\n')
(D/'README.md').write_text('\n'.join(lines))
print(D/'README.md')
