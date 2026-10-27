from __future__ import annotations
import gzip,hashlib,json,math,sys
from pathlib import Path
sys.path.insert(0,'/workspace/omnichunk')
from omnichunk.retrieval_eval import EvidenceSpan,score_evidence
from dataclasses import asdict
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
W=Path('/workspace/work/omnichunk-v3')
jobs=[(W/f'dev/code-files/{m}/baseline',W/'code-files/development') for m in ['multilingual','english']]+[(W/'dev/code-files/english/chonkie-sentence-96',W/'code-files/development')]+[(W/f'dev/code/{m}/semantic-code',W/'code/development') for m in ['multilingual','english']]+[(W/'dev/turkish/semantic-code',W/'turkish/development')]
checks=0;cells=0;results=[]
for out,source in jobs:
 raw=gzip.decompress((out/'report.json.gz').read_bytes());r=json.loads(raw);corpus=load_corpus(source)
 assert r['corpus_manifest_sha256']==corpus.manifest_hash;checks+=1
 assert r['environment']['runtime_git_revision']=='e63c7f097a8ccec39262c8fb00fb2375a3e5283d';checks+=1
 docs={d.source_id:d.text.encode('utf-8') for d in corpus.documents if d.split=='dev'};queries={q.query_id:q for q in corpus.queries if q.split=='dev'}
 counter=benchmark_counter('tokens',r['configuration']['tokenizer'],include_special_tokens=True)
 h=hashlib.sha256()
 with gzip.open(out/'vectors.json.gz','rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 assert h.hexdigest()==r['configuration']['dense_embeddings']['artifact_sha256'];checks+=1
 for c in r['candidates']:
  assert c['status']=='ok' and c['embedding_calls']==0;checks+=1;cells+=1
  pmap={p['passage_id']:p for p in c['passages']};ends={}
  for p in c['passages']:
   raw_source=docs[p['source_id']];start,end=p['start'],p['end'];prev=ends.get(p['source_id'],0)
   assert start>=prev and not raw_source[prev:start].decode('utf-8').strip();checks+=1
   assert raw_source[start:end].decode('utf-8')==p['text'];checks+=1
   assert counter(p['text'])<=c['chunk_capacity'];checks+=1;ends[p['source_id']]=end
  for sid,raw_source in docs.items():assert not raw_source[ends.get(sid,0):].decode('utf-8').strip();checks+=1
  assert len(c['per_query'])==len(queries);checks+=1
  for row in c['per_query']:
   q=queries[row['query_id']];assert row['query']==q.text;checks+=1
   selected=[pmap[x] for x in row['budget_passage_ids']]
   used=counter('\n\n'.join(p['text'] for p in selected)) if selected else 0
   assert used==row['budget_used'] and used<=r['configuration']['retrieval_budget'];checks+=1
   scores=asdict(score_evidence([EvidenceSpan(p['source_id'],p['start'],p['end']) for p in selected],q.evidence))
   assert scores==row['evidence_at_budget'];checks+=1
  for metric in ['precision','recall','iou']:
   actual=sum(q['evidence_at_budget'][metric] for q in c['per_query'])/len(queries)
   assert math.isclose(actual,c['summary']['all']['evidence_at_budget'][metric],rel_tol=0,abs_tol=1e-12);checks+=1
 results.append({'directory':str(out),'cells':len(r['candidates']),'queries':len(queries),'report_sha256':hashlib.sha256(raw).hexdigest(),'vector_artifact_sha256':h.hexdigest()})
failed=json.loads((W/'dev/code-files/english/chonkie-sentence-64-failed/report.json').read_text());assert failed['candidates'][0]['status']=='error' and 'summary' not in failed['candidates'][0];checks+=1
(W/'adapter-audit/baseline-artifact-audit.json').write_text(json.dumps({'status':'passed','checks':checks,'successful_cells':cells,'explicit_failure_cells':1,'scope':'Exact corpus/source+UTF8 budget conformance, frozen vector hashes, zero evaluation inference, all per-query evidence scores/means','jobs':results},indent=2)+'\n')
print('PASSED',checks,'checks',cells,'successfulcells',flush=True)
