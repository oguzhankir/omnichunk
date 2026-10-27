from __future__ import annotations
import gzip,hashlib,json,math,sys
from pathlib import Path
from dataclasses import asdict
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v3';sys.path.insert(0,str(H))
from omnichunk.retrieval_eval import EvidenceSpan,score_evidence,score_ranking
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
F=W/'freeze-before-validation-v3.json';assert hashlib.sha256(F.read_bytes()).hexdigest()=='54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334';f=json.loads(F.read_text())
for name,digest in f['harness_files'].items():assert hashlib.sha256((H/name).read_bytes()).hexdigest()==digest
roots=[('turkish','multilingual',W/'validation/turkish')]+[(d,m,W/f'validation/{d}/{m}') for d in ['code','code-files'] for m in ['multilingual','english']]
checks=0;cells=0;failed_cells=0;results=[];coverage={}
for domain,model,base in roots:
 groupfile=base/'conformance-groups.json'
 if not groupfile.exists():continue
 groups=json.loads(groupfile.read_text());source=W/domain/'validation';corpus=load_corpus(source);docs={d.source_id:d.text.encode('utf-8') for d in corpus.documents};queries={q.query_id:q for q in corpus.queries};covered=set()
 expected=f['validation_commitments'][domain].get('validation_manifest_sha256',f['validation_commitments'][domain].get('manifest_sha256'));assert corpus.manifest_hash==expected;checks+=1
 completed=set()
 events=(W/'validation/baseline-events.jsonl').read_text().splitlines()
 for line in events:
  try:e=json.loads(line)
  except json.JSONDecodeError:continue
  if e['event']=='group-completed':completed.add(e['directory'])
 for label,tools,caps in groups['groups']:
  out=base/label
  if str(out) not in completed:continue
  raw=gzip.decompress((out/'report.json.gz').read_bytes());r=json.loads(raw)
  assert r['corpus_manifest_sha256']==expected;checks+=1
  assert r['environment']['runtime_git_revision']=='e63c7f097a8ccec39262c8fb00fb2375a3e5283d';checks+=1
  embed=r['configuration']['dense_embeddings'];model_freeze=next(m for m in f['models'] if m['revision']==embed['model_revision']);assert embed['producer_metadata']['model_files']==model_freeze['files'];checks+=1
  assert r['configuration']['include_special_tokens'] is True and r['configuration']['retrieval_budget']==512;checks+=1
  count=benchmark_counter('tokens',r['configuration']['tokenizer'],include_special_tokens=True)
  h=hashlib.sha256()
  with gzip.open(out/'vectors.json.gz','rb') as stream:
   for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
  assert h.hexdigest()==embed['artifact_sha256'];checks+=1
  for c in r['candidates']:
   assert c['status']=='ok' and c['embedding_calls']==0;checks+=1;cells+=1;covered.add((c['tool'],c['chunk_capacity']))
   pmap={p['passage_id']:p for p in c['passages']};assert len(pmap)==len(c['passages']);checks+=1;ends={}
   for p in c['passages']:
    raw_source=docs[p['source_id']];start,end=p['start'],p['end'];prev=ends.get(p['source_id'],0)
    assert start>=prev and not raw_source[prev:start].decode('utf-8').strip();checks+=1
    assert raw_source[start:end].decode('utf-8')==p['text'];checks+=1
    assert count(p['text'])<=c['chunk_capacity'];checks+=1;ends[p['source_id']]=end
   for sid,raw_source in docs.items():assert not raw_source[ends.get(sid,0):].decode('utf-8').strip();checks+=1
   assert len(c['per_query'])==len(queries);checks+=1
   for row in c['per_query']:
    q=queries[row['query_id']];assert row['query']==q.text;checks+=1
    selected=[pmap[x] for x in row['budget_passage_ids']];used=count('\n\n'.join(p['text'] for p in selected)) if selected else 0
    assert used==row['budget_used'] and used<=512;checks+=1
    scores=asdict(score_evidence([EvidenceSpan(p['source_id'],p['start'],p['end']) for p in selected],q.evidence));assert scores==row['evidence_at_budget'];checks+=1
    ranks=[pmap[x['passage_id']] for x in row['ranks']]
    at_k=asdict(score_evidence([EvidenceSpan(p['source_id'],p['start'],p['end']) for p in ranks],q.evidence));assert at_k==row['evidence_at_k'];checks+=1
    qrels={p['passage_id']:1.0 for p in c['passages'] if any(p['source_id']==e.source_id and max(p['start'],e.start)<min(p['end'],e.end) for e in q.evidence)}
    ranking=asdict(score_ranking([p['passage_id'] for p in ranks],qrels,k=5));assert ranking==row['ranking'];checks+=1
   for metric in ['precision','recall','iou']:
    actual=sum(q['evidence_at_budget'][metric] for q in c['per_query'])/len(queries);assert math.isclose(actual,c['summary']['all']['evidence_at_budget'][metric],rel_tol=0,abs_tol=1e-12);checks+=1
  results.append({'directory':str(out),'cells':len(r['candidates']),'queries':len(queries),'report_sha256':hashlib.sha256(raw).hexdigest(),'vector_artifact_sha256':h.hexdigest()})
 for failure in groups['failures']:
  tool,cap=failure['tool'],failure['capacity'];path=base/'failures'/f'{tool}-{cap}'/'report.json'
  if not path.exists():continue
  r=json.loads(path.read_text());assert all(c['status']!='ok' and 'summary' not in c for c in r['candidates']);checks+=1;failed_cells+=1;covered.add((tool,cap))
 coverage[f'{domain}-{model}']={'represented_cells':len(covered),'expected_cells':20,'successful_or_explicit_failure':sorted(covered)}
complete=len(coverage)==5 and all(c['represented_cells']==20 for c in coverage.values())
result={'status':'passed' if complete else 'partial-passed','freeze_sha256':hashlib.sha256(F.read_bytes()).hexdigest(),'checks':checks,'successful_cells':cells,'explicit_failure_cells':failed_cells,'scope':'Frozenharness unchanged; frozenmodel snapshots; actuale63runtime; corpus/vector hashes; exactcanonical UTF8source+nativepayloadbudgets; allquery joinedbudgets/evidence/top5/rankingmetrics/means; no newmodelcalls','coverage':coverage,'jobs':results}
(W/'adapter-audit/validation-baseline-artifact-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(result['status'],checks,cells,failed_cells,flush=True)
