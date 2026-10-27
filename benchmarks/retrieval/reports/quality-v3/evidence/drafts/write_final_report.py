from __future__ import annotations
import csv,datetime,gzip,hashlib,json
from pathlib import Path

W=Path('/workspace/work/omnichunk-v3');D=W/'drafts';D.mkdir(exist_ok=True)
INPUTS={}
def read(p):
 b=p.read_bytes();INPUTS[str(p.relative_to(W))]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(v):return f'{v:.6f}'
def ci(m):
 if m is None:return 'unavailable'
 bounds=m.get('bootstrap_delta_ci_95');return f"{m['mean_delta']:+.6f} [{bounds[0]:+.6f}, {bounds[1]:+.6f}]" if bounds is not None else f"{m['mean_delta']:+.6f} [unavailable]"
def wtl(m):return '/'.join(str(m[k]) for k in ['wins','ties','losses']) if m else 'unavailable'
freeze=read(W/'freeze-before-validation-v3.json');assert digest(W/'freeze-before-validation-v3.json')=='54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334'
refs=read(W/'reference-choices-before-validation.json')['choices'];
if (W/'validation/candidate-results-summary.json').exists():read(W/'validation/candidate-results-summary.json')
read(W/'reference-selection-commitment.json');read(W/'review-before-validation-v3.json')
CASES=[('turkish','multilingual'),('code','multilingual'),('code','english'),('code-files','multilingual'),('code-files','english')]
PROFILES=['omnichunk','omnichunk-prose-compact','omnichunk-code-compact']
NAMES={'omnichunk':'default','omnichunk-prose-compact':'prose-compact','omnichunk-code-compact':'code-compact'}
ALL={};pairs={};cells=[];missing=[]

def cellrow(domain,model,role,c,x,path):
 dense=x.get('configuration',{}).get('dense_embeddings') or {};prod=dense.get('producer_metadata',{});loads={(v['tool'],v['chunk_capacity']):v for v in prod.get('candidate_workloads',[])};load=loads.get((c['tool'],c['chunk_capacity']),{});m=c.get('summary',{}).get('all',{}).get('evidence_at_budget',{})
 return {'domain':domain,'model':model,'role':role,'tool':c['tool'],'capacity':c['chunk_capacity'],'retrieval_budget':x.get('configuration',{}).get('retrieval_budget',512),'status':c['status'],'recall':m.get('recall',''),'precision':m.get('precision',''),'iou':m.get('iou',''),'vectors':c.get('chunks',''),'native_passage_tokens':load.get('passage_input_tokens',''),'chunk_seconds_median':c.get('chunk_seconds_median',''),'artifact':str(path.relative_to(W)),'artifact_sha256':INPUTS[str(path.relative_to(W))]['sha256'],'status_detail':c.get('detail','')}

for domain,model in CASES:
 case=W/'validation'/domain/(model if domain!='turkish' else '')
 base={};fail=[];cand={}
 for p in sorted(case.glob('baseline*/report.json*')):
  x=read(p)
  for c in x['candidates']:
   if c['status']=='ok':
    k=(c['tool'],c['chunk_capacity']);assert k not in base;base[k]=c
   else:fail.append(c)
 for p in sorted((case/'failures').glob('*/report.json')) if (case/'failures').exists() else []:
  x=read(p);fail+=x['candidates']
 p=case/'candidate-final-d0/report.json.gz'
 if p.exists():
  x=read(p)
  for c in x['candidates']:cand[(c['tool'],c['chunk_capacity'])]=c
  audit=read(p.parent/'cache-audit.json')
 else:missing.append(domain+'/'+model);audit=None
 ALL[(domain,model)]={'baseline':base,'failures':fail,'candidate':cand,'audit':audit}
 cp=W/'comparisons/validation'/domain/(model if domain!='turkish' else '')
 for p in sorted(cp.glob('*/*/vs-*.json')):
  x=read(p)
  for comp in x['comparisons']:
   k=(domain,model,x['configuration']['retrieval_budget'],x['candidate_tool'],comp['chunk_capacity'],x['baseline_tool']);pairs[k]=comp['slices']['all']['metrics']
 front=W/'frontier/validation'/domain/(model if domain!='turkish' else '')
 for p in sorted(front.glob('*/budget-*.report.json')):
  x=read(p);role='candidate' if p.parent.name=='candidate-final-d0' else 'baseline'
  for c in x['candidates']:cells.append(cellrow(domain,model,role,c,x,p))
 for p in sorted((case/'failures').glob('*/report.json')) if (case/'failures').exists() else []:
  x=read(p)
  for c in x['candidates']:cells.append(cellrow(domain,model,'baseline-preflight-failure',c,x,p))

def metric(c):return c['summary']['all']['evidence_at_budget']
def paired(d,m,cap,profile,ref,budget=512):return pairs.get((d,m,budget,profile,cap,ref),{}).get('recall')
def names_best(base,cap):
 values=[(t,c) for (t,k),c in base.items() if k==cap and t not in ['omnichunk','fixed']]
 return max(values,key=lambda tc:(metric(tc[1])['recall'],metric(tc[1])['precision'],-tc[1]['chunks'],tc[0]))
def label(d,m,cap):return f'{d} / {"ML" if m=="multilingual" else "EN"} / {cap}'

f=D/'validation-outcomes.csv';fields=['domain','model','role','tool','capacity','retrieval_budget','status','recall','precision','iou','vectors','native_passage_tokens','chunk_seconds_median','artifact','artifact_sha256','status_detail']
with f.open('w',newline='') as out:writer=csv.DictWriter(out,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(cells)
# Record all evidence sources used in narrative sections too.
old=(D/'README.md').read_text();INPUTS['drafts/README.md']={'sha256':digest(D/'README.md'),'bytes':(D/'README.md').stat().st_size}
parent_dev=read(W/'parent-retrieval/candidate-final-c1/combined-summary.json');parent_val=read(W/'parent-retrieval/validation/combined-summary.json');parent_dev_pairs=read(W/'parent-retrieval/candidate-final-c1/paired.json');parent_val_pairs=read(W/'parent-retrieval/validation/paired.json');context=read(W/'context-dense-development/summary.json')
for p in [W/'parent-retrieval/validation/artifact-audit.json',W/'parent-retrieval/validation/manifest.json',W/'parent-retrieval/validation/identity-cache-audit.json',W/'dataset-readme-reproduction-audit.json']:
 if p.exists():read(p)
def parentmean(summary,profile,cap,method,target):
 return next(r['summary']['recall'] for r in summary['outputs'] if r['version'].startswith('final-') and r['tool']==profile and r['capacity']==cap and r['method']==method and r['expansion_target']==target)
def parentpair(summary,profile,cap,method,target):
 return next(r['versus_own_raw']['recall'] for r in summary['comparisons'] if r['version'].startswith('final-') and r['tool']==profile and r['capacity']==cap and r['method']==method and r['expansion_target']==target)

L=['''# Retrieval quality and cost on real-source corpora, v3

**OmniChunk shows a narrow, descriptive code-retrieval advantage in one English encoder/64-token cell against the strongest observed conforming named strategy, while tying the fixed splitter there. Broad superiority and a Pareto advantage are not established.** Multilingual isolated code remains weaker than its strongest named control, and compact code regresses substantially at 96 tokens on real files. The retained structural default has separate gains against prior OmniChunk in some settings. Those secondary gains do not replace the frozen primary-profile results.
''']
if missing:L.append('**INCOMPLETE SNAPSHOT — pending final candidate cases: '+', '.join(missing)+'. Refresh this report before publication.**\n')
L.append('''## Frozen experiment and interpretation

Prior-main baseline: `e63c7f097a8ccec39262c8fb00fb2375a3e5283d`. Final runtime and harness:
[`d0bd4b5ea10ff458313a82b3340c8f1a3f49e572`](https://github.com/oguzhankir/omnichunk/tree/d0bd4b5ea10ff458313a82b3340c8f1a3f49e572).
The source/model/settings freeze is [freeze-before-validation-v3.json](evidence/freeze-before-validation-v3.json), SHA256 `54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334`.
The two earlier freeze records were superseded before validation release to finish correctness/review repairs; their hashes and reasons remain preserved. No runtime/profile/model setting was selected or modified after release. Evidence/data/documentation publication is separate from this frozen runtime.

The [reference choices](evidence/reference-choices-before-validation.json) and its [commitment](evidence/reference-selection-commitment.json) fixed the primary candidate and named comparator from development before release: Turkish uses prose-compact; both code views use code-compact. The selected named strategy maximized development primary recall, then precision and fewer vectors, with a stable name tie-breaker. Fixed is always a separate control. All three candidate profiles and every admitted baseline remain visible. An observed-best validation mean is reported separately as an **ex-post descriptive control**, not a replacement for the preselected comparator.

| Protocol item | Frozen value |
| --- | --- |
| Native chunk capacities | 64 and 96, special tokens included |
| Primary complete retrieved context | 512 native tokens, two-newline separators included, whole ranked prefix |
| Sensitivity contexts | 128 and 256, predeclared; shared frozen vectors/rankings, no new inference |
| Ranking metric | Separate top-k 5, not interchangeable with byte evidence recall |
| Primary overlap/context | Zero overlap and no derived context |
| Models | Multilingual MiniLM-L12-v2 `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`; English MiniLM-L6-v2 `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` |
| Encoder/input contract | Real local pretrained Transformer + mean pooling (+ Normalize for English), no prompts; full native inputs, overflow rejected rather than truncated |
| Runtime | CPU, batch 32, two Torch threads and two interop threads; three chunking repetitions |
| Uncertainty | 2,000 paired cluster-bootstrap draws, seed 0, percentile 95% intervals; 16 repository clusters for each code view, 60 source-passage clusters for Turkish |

Intervals are **unadjusted under many capacities, profiles, references, budgets and slices**. They are descriptive, not family-wise controlled significance tests. The two encoders and two code views are correlated measurements; they are not independent replications or extra datasets. Native tokenizers differ, so cross-model score differences are not a controlled model ranking. Query-mean byte precision/recall/IoU do not measure generated-answer correctness, minimal support sufficiency or production adoption.

## Primary 512-token validation results

ML = multilingual encoder, EN = English encoder. W/T/L counts paired query recall wins/ties/losses, with tolerance 1e-12. Each code row has 64 queries on isolated functions or 56 correlated queries on files; Turkish has 120. References below are exactly the pre-release development choices. Missing/nonconforming cells have no invented zero score.

| View / encoder / capacity | Frozen candidate | Recall | Preselected named reference | Reference recall | Δ recall [unadjusted 95% interval] | W/T/L |
| --- | --- | --- | --- | --- | --- | --- |''')
primary=[]
for r in refs:
 d,m,cap=r['domain'],r['model'],r['chunk_capacity'];profile=r['candidate_profile'];ref=r['named_reference'];case=ALL[(d,m)];c=case['candidate'].get((profile,cap));b=case['baseline'].get((ref,cap))
 if c is None:L.append(f'| {label(d,m,cap)} | {NAMES[profile]} | pending | {ref} | {fmt(metric(b)["recall"]) if b else "failed"} | pending | pending |');continue
 pair=paired(d,m,cap,profile,ref);L.append(f'| {label(d,m,cap)} | {NAMES[profile]} | {fmt(metric(c)["recall"])} | {ref} | {fmt(metric(b)["recall"]) if b else "failed conformance"} | {ci(pair)} | {wtl(pair)} |')
 primary.append({'domain':d,'model':m,'capacity':cap,'profile':profile,'recall':metric(c)['recall'],'reference':ref,'paired_recall':pair})
L.append('''
The fixed control and the observed highest-mean named control are distinct checks. “Observed best” below excludes fixed and prior OmniChunk and is chosen **after seeing validation only to expose the strongest observed control**; it does not retroactively change the frozen comparison. Native `semantic-code` is semantic-text-splitter's CodeSplitter for Python and its documented text fallback for prose, not a new independent library.

| View / encoder / capacity | Fixed recall | Candidate − fixed [95% interval] | Observed best named: recall | Candidate − observed best [95% interval] | Vectors: candidate / fixed / observed best |
| --- | --- | --- | --- | --- | --- |''')
for r in refs:
 d,m,cap=r['domain'],r['model'],r['chunk_capacity'];profile=r['candidate_profile'];case=ALL[(d,m)];c=case['candidate'].get((profile,cap));fixed=case['baseline'][('fixed',cap)];name,best=names_best(case['baseline'],cap)
 if c is None:L.append(f'| {label(d,m,cap)} | {fmt(metric(fixed)["recall"])} | pending | {name}: {fmt(metric(best)["recall"])} | pending | pending |');continue
 L.append(f'| {label(d,m,cap)} | {fmt(metric(fixed)["recall"])} | {ci(paired(d,m,cap,profile,"fixed"))} | {name}: {fmt(metric(best)["recall"])} | {ci(paired(d,m,cap,profile,name))} | {c["chunks"]} / {fixed["chunks"]} / {best["chunks"]} |')
# Exact scoped example; do not generalize across cells or models.
e=ALL[('code','english')];c=e['candidate'][('omnichunk-code-compact',64)];b=e['baseline'][('semchunk',64)];f=e['baseline'][('fixed',64)];em=paired('code','english',64,'omnichunk-code-compact','semchunk');fm=paired('code','english',64,'omnichunk-code-compact','fixed')
L.append(f'''\nThe narrow favorable cell is isolated code / EN / 64: compact recall {fmt(metric(c)['recall'])} versus observed-best named semchunk {fmt(metric(b)['recall'])}; paired delta {ci(em)}, W/T/L {wtl(em)}. Its {c['chunks']} vectors versus {b['chunks']} are {100*(1-c['chunks']/b['chunks']):.2f}% fewer, while precision/IoU and token work remain separately reported. **Fixed recall is {fmt(metric(f)['recall'])} with paired delta {ci(fm)}.** This is an exact recall tie with a simple control, not evidence of unique general superiority. The positive named-comparison interval is unadjusted and was inspected among many cells.\n''')
for model in ['multilingual','english']:
 case=ALL[('code-files',model)];oldbase=case['baseline'][('omnichunk',96)];compact=case['candidate'].get(('omnichunk-code-compact',96))
 if compact is not None:
  mp=paired('code-files',model,96,'omnichunk-code-compact','omnichunk')
  L.append(f'**Real-file / {model} / 96 compact regression:** prior OmniChunk recall {fmt(metric(oldbase)["recall"])} → compact {fmt(metric(compact)["recall"])}; paired delta {ci(mp)}, W/T/L {wtl(mp)}. This frozen primary-profile loss remains part of the conclusion.\n')
L.append('''## Default behavior and complete profile costs

The structural default is a secondary retained profile, not a replacement for the frozen compact primary. Compare it with prior OmniChunk to assess the general correctness repairs. Its larger real-file 96-token recall can coexist with a substantial compact-profile loss; report both. Payload tokens are complete native model inputs per indexed chunk, including special tokens. Vector count and token work are different costs.

| View / encoder / capacity | Prior Omni recall → final default | Paired Δ recall [95% interval] | Prior → default vectors | Default precision / IoU |
| --- | --- | --- | --- | --- |''')
for d,m in CASES:
 case=ALL[(d,m)]
 for cap in [64,96]:
  b=case['baseline'][('omnichunk',cap)];c=case['candidate'].get(('omnichunk',cap))
  if c is None:L.append(f'| {label(d,m,cap)} | pending | pending | pending | pending |');continue
  mt=metric(c);L.append(f'| {label(d,m,cap)} | {fmt(metric(b)["recall"])} → {fmt(mt["recall"])} | {ci(paired(d,m,cap,"omnichunk","omnichunk"))} | {b["chunks"]} → {c["chunks"]} | {fmt(mt["precision"])} / {fmt(mt["iou"])} |')
L.append('''
Every final profile's primary quality and index work is retained here; identical profiles on a corpus remain visible rather than counted as independent wins. [validation-outcomes.csv](validation-outcomes.csv) additionally contains every successful 128/256/512 cell and explicit preflight failures with exact artifact hashes, including all rivals.

| View / encoder / capacity | Profile | Recall | Precision | IoU | Vectors | Native passage tokens |
| --- | --- | --- | --- | --- | --- | --- |''')
primary_rows=[r for r in cells if r['role']=='candidate' and r['retrieval_budget']==512]
for r in primary_rows:L.append(f'| {label(r["domain"],r["model"],r["capacity"])} | {NAMES[r["tool"]]} | {fmt(r["recall"])} | {fmt(r["precision"])} | {fmt(r["iou"])} | {r["vectors"]} | {r["native_passage_tokens"]} |')
L.append('''
At small context budgets, a different profile/control can win; the complete predeclared sensitivity table and paired files preserve this instead of selecting another validation winner. Index compaction alone cannot establish a Pareto advantage when relevant evidence or precision regresses.

## Data and attribution limits

[Published corpus overview](../../corpus_external_v3/README.md) documents all source revisions, licenses, import commands and release records.

| Corpus | Development / validation | Evidence contract |
| --- | --- | --- |
| Belebele Turkish | 60 / 60 source passages, 120 / 120 original question stems; CC-BY-SA-4.0 | Whole originating passage, choices omitted; some stems are underspecified without choices. Not independently audited minimal support or answer accuracy. |
| Isolated CodeSearchNet Python | 64 / 64 functions and proxy queries, 16 / 16 repository clusters; exact-commit MIT licenses retained | Human documentation first paragraph queried against docstring-stripped canonical functions. Whole-function gold omits dependency/class/import completeness. |
| Correlated real-file code | 37 / 35 original files, 56 / 56 existing eligible questions, 15 / 16 repository clusters | Complete original neighboring code, every AST docstring removed; sole-body docstrings become `pass`; source-anchored function gold rebased into canonical UTF-8 bytes. No synthetic joins. |

The real-file task is a correlated subset/view of the isolated-function questions, not another independent sample. Its declared original-file limit is 30,000 Unicode characters with Python 3 parsing and exact URL-anchor/AST mapping. Development excludes seven resource-limit queries and one Python 2 query; validation excludes five resource-limit and three Python 3 parse queries. Fetch and eligible function mappings succeed; exact and normalized complete query-substring audits after stripping docstrings find zero matches. These eligibility and removal rules were declared before view scores.

The pinned sources are Belebele `7899cdfa4e1e0d733fd77c848e2c273cb1d32be2` and CodeSearchNet `bd0cf261e357a3eb5c8fba490d23ec1a1cd59555`; original contributor/source URLs, function paths, exact repository commits and MIT license texts remain attached. No source code is executed. MIT-only selection, docstring proxies, translated Turkish, file-size/syntax eligibility and possible model pretraining overlap limit generalization to production users.

XQuAD was rejected as fresh validation because all 48 articles were previously observed. TQuAD was not redistributed because its original pinned tree had no license declaration; third-party mirror labels were not assumed to grant rights. Initial CodeSearchNet full-docstring overflow was rejected before valid scores; the frozen amendment uses `full.split(chr(10) + chr(10))[0].strip()` for all selected functions without reselection. Initial original-function bundles were replaced by separate real functions before scoring. Superseded commitments and those amendments remain available.

## Custody, release and independent byte checks

Selection, reference choices, runtime/model/settings freeze and clean code/security reviews all precede validation release. Custody was procedural within shared agent workspaces, not an independent external custodian. Turkish was decrypted with its retained key. For **both code views, transient AES keys were unavailable after agent reactivation**. After the freeze the custodian reconstructed the datasets from pinned upstream/commit sources using the frozen importers and recovered both exact previously committed manifest hashes. The release records disclose reconstruction, not successful decryption; no score-based edits, profile changes or source changes were made. Public upstream availability limits blindness claims. Validation is now observed and must not be reused as a new unseen tuning set.

Final validation manifest commitments are Turkish `7e4f9a1916689380289ce437f22df0a4e30677a62a15d3ea83256f84a8706b8f`, isolated code `ddbe1ee7172576c20339ed6e261bc066bb4269612b2f04232cd89a07498be46f`, and real-file code `dcfb7769bffade3c0bf9e3b6cc3f4d77822ce15595e668d430d606fa7c0e24b7`. The six development/validation importers were independently rerun in scratch using Python 3.12.14 and isolated PyArrow 23.0.1: all six manifests match exactly and 520 source/license byte checks pass. Dataset/documentation publication did not alter manifest/protocol/builder/attribution bytes.

## Adapter conformance and timing scope

Ten strategies are declared per baseline view: OmniChunk, fixed, semchunk, LangChain generic recursive and native code, semantic-text-splitter text/Markdown and native tree-sitter CodeSplitter, LlamaIndex token and sentence, and Chonkie sentence. Distinct strategies from one package are not independent libraries. The recursive Chonkie count-only token contract remains unsupported; native sentence results are kept where conforming. Exact canonical source, native complete-payload budget and overlap checks precede inference. A failed strategy/capacity contributes no retrieval score, no hidden fallback, no per-file repair and no zero aggregate.

The five completed baseline views contain 95 successful primary strategy/capacity cells and five explicit failures out of 100. Final candidates declare 30 cells (three profiles × two capacities × five view/model cases). Failed baseline cells are carried through the comparison inventory as unavailable, including valid96-only controls in separate reports. All final models/packages/sources and the two superseded pre-release freeze records remain fingerprinted.

Candidate preparation reuses baseline vectors only with exact role/text and full model/preprocessing-contract identity, and separately records new encoder work. Baseline encoding timings are not copied as candidate cost. Shared preparation includes deduplication and first model calls; query/passages have separate new/reused counts. Frozen-vector ranking/replay does not measure online model latency. Chunking, preparation and ranking times have different scopes and shared CPU contention; no per-library cold-start, production latency, memory SLA or throughput leadership is claimed.
''')
# Reuse the immutable development investigation record, without its stale draft/freeze conclusions.
for heading,next_heading in [('## Every development trial and why it is retained or superseded','## Negative context study'),('## Negative context study','## Public options and compatibility'),('## Public options and compatibility','## Failed attempts, pending work and final validation requirements')]:
 text=old[old.index(heading):old.index(next_heading)]
 text=text.replace('running jobs remain pending rather than omitted as losses or wins','the development snapshot fixes completed inputs; later frozen reruns and final validation have separate artifacts')
 L.append(text)
L.append('''Additional final correctness/review repairs preserve mixed Markdown ownership and tight-list literal fences, reject infeasible protected compact layouts with actionable errors, and distinguish actual Python AST docstrings from triple-quoted data. These repairs were completed before the final freeze, with meaningful regressions; review findings and superseded freeze records remain preserved. Correctness constraints take precedence over a more favorable intermediate mean. General options and [the runnable policy recipe](../../../../docs/usage.md) document independent profile selection and index invalidation.

## Parent/window stress test: development gain did not replicate

A secondary workflow grid was fixed before release: child capacities 64/96, source-window and public-hierarchy targets 128/256/512, a complete 512-token final context cap, and deterministic union/prefix-stop assembly. It reuses completed frozen raw ranks/vectors with **zero additional encoder or ranking calls**. Existing preparation still had encoder cost. Source-window controls are retained for every named rival; this is a diagnostic workflow study, not a promoted feature/profile or new primary claim.

Default/prose-compact validation hierarchy inputs are independently verified as actual public native leaves (1,336 at 64; 887 at 96), with exact source/range/text/passage-ID/order identity and 280/280 anchor ancestry mappings per capacity/target. Compact-code uses different leaf payloads and remains explicitly span-mapped with containing-parent/window fallbacks; no native compact-code hierarchy index is claimed. The secondary cache audit verifies all 2,105 required role/text keys and 4,446 source/budget checks. Full workflows retain 154 declared rows: 149 scored on 56 queries, five frozen adapter failures; 432 matched rival comparisons include 24 explicitly unavailable cases. These are correlated views of the same 16-repository code validation sample.

The final default child96/window128 development gain reverses on validation. No parameter search or workflow promotion follows the reversal. Parent-study intervals separately use 2,000 repository-bootstrap draws and seed 20261027, are unadjusted, and remain exploratory.

| Split | Raw default child96 recall | Window128 recall | Δ recall [unadjusted 95% interval] | W/T/L |
| --- | --- | --- | --- | --- |''')
for name,summary,pairsummary in [('Development',parent_dev,parent_dev_pairs),('Validation',parent_val,parent_val_pairs)]:
 raw=parentmean(summary,'omnichunk',96,'raw-prefix',512);window=parentmean(summary,'omnichunk',96,'source-window',128);mp=parentpair(pairsummary,'omnichunk',96,'source-window',128);L.append(f'| {name} | {fmt(raw)} | {fmt(window)} | {ci(mp)} | {wtl(mp)} |')
L.append('''
Within this secondary parent/window study, every positive final-profile validation recall delta has an interval crossing zero; large default child96/window512 and hierarchy512 regressions have intervals below zero. The [complete secondary record](evidence/parent-retrieval/validation/README.md) retains every method, rival window, mapping label and failure. Its exact source/budget/metric audit passes 72,807 checks, and finalization binds 154 workflow rows plus 8,344 available per-query rows. The 280 missing slots belong to frozen failures, not invented results.

## Verification and reuse

Before release, **1,655 tests passed, 36 optional tests were skipped**, with **90.71% combined statement/branch coverage measured with branch collection enabled**. This is not 90.71% branch-only coverage: the recorded branch-only component is approximately 85.03%. Ruff/format, strict mypy, structural scenarios and strict MkDocs passed on the frozen source, and code/security reviews completed without findings at that head. Final evidence-publication CI/package/audit results remain recorded separately from these pre-release source gates.

The complete final outcome CSV and hashed input ledger make the generated tables auditable. Raw report means, per-query scores, conformance failures, all paired comparisons, source/repository cluster maps, preparation cache audits, exact freeze/release records, environment/model hashes and archived trial source commits remain linked under `evidence/`. The [development catalog](development-outcomes.csv) retains lexical screens separately from real pretrained dense trials. All rejected trials, original negative context results and the negative held-out parent/window replication remain available.

Use these results to choose and test an explicit profile on representative local data. They support a scoped English function-retrieval improvement in one English 64-token cell against named controls and identify meaningful default repairs and cost tradeoffs. They do not establish universal chunking leadership, answer accuracy, an independent production design-partner result, or a completed quality milestone. No runtime change or new tuning is justified by these now-observed validation labels.
''')
L.append(f'\nGenerated snapshot: {datetime.datetime.now(datetime.timezone.utc).isoformat()}; {len(primary_rows)}/30 candidate primary rows available. Validation outcome CSV SHA256 `{digest(D/"validation-outcomes.csv")}`.\n')
(D/'README-final.md').write_text('\n'.join(L))
ledger={'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'freeze_sha256':digest(W/'freeze-before-validation-v3.json'),'pending_cases':missing,'all_source_inputs':INPUTS,'primary_rows':primary,'candidate_primary_rows':len(primary_rows),'validation_csv_rows':len(cells),'validation_csv_sha256':digest(D/'validation-outcomes.csv'),'report_sha256':digest(D/'README-final.md'),'no_inference_or_tuning':True}
(D/'final-report-inputs.json').write_text(json.dumps(ledger,indent=2)+'\n')
print(json.dumps({'report':str(D/'README-final.md'),'primary_rows':len(primary_rows),'pending':missing,'input_artifacts':len(INPUTS),'csv_rows':len(cells),'report_sha256':ledger['report_sha256']}))
