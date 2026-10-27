from __future__ import annotations
import csv,datetime,gzip,hashlib,json
from pathlib import Path

W=Path('/workspace/work/omnichunk-v3');D=W/'drafts'
H=lambda b:hashlib.sha256(b).hexdigest()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
paths=[]
for root in [W/'dev',W/'frontier/dev']:
 for p in root.rglob('*'):
  if p.is_file() and (p.name in ['report.json','report.json.gz'] or p.name.endswith('.report.json')):paths.append(p)
for p in (W/'context-dense-development').glob('*-budget-*.json.gz'):paths.append(p)
for parent in Path('/workspace/work/omnichunk-quality/screen').glob('v3-*'):
 paths.extend(parent.rglob('report.json'))
rows=[];inputs=[]
for p in sorted(paths):
 try:x=read(p)
 except (ValueError,EOFError):continue
 if x.get('configuration',{}).get('split') not in [None,'dev']:raise ValueError('Non-development input rejected')
 raw=p.read_bytes(); rel=str(p.relative_to(W)) if p.is_relative_to(W) else 'external-quality-screen/'+str(p.relative_to('/workspace/work/omnichunk-quality/screen'))
 inputs.append({'path':rel,'absolute_input':str(p),'sha256':H(raw),'bytes':len(raw)})
 config=x.get('configuration',{});dense=config.get('dense_embeddings',{}) or {};producer=dense.get('producer_metadata',{});workloads={(i['tool'],i['chunk_capacity']):i for i in producer.get('candidate_workloads',[])}
 for c in x.get('candidates',[]):
  summary=c.get('summary',{});summary=summary.get('all',summary);metric=summary.get('evidence_at_budget',summary);workload=workloads.get((c['tool'],c['chunk_capacity']),{})
  rows.append({'artifact':rel,'artifact_sha256':H(raw),'corpus_id':x.get('corpus_id','code-context-study'),'manifest_sha256':x.get('corpus_manifest_sha256',''),'runtime':x.get('environment',{}).get('runtime_git_revision',''),'model':dense.get('model_id',p.name.split('-budget-')[0] if 'context-dense' in str(p) else ''),'model_revision':dense.get('model_revision',''),'retriever':'real-pretrained-dense' if c['status']=='ok' else 'not-run-adapter-preflight','stage':'adapter-preflight-failure' if c['status']!='ok' else 'context-study' if 'context-dense' in str(p) else 'sensitivity-frozen-replay' if '/frontier/' in str(p) else 'primary-development','tool':c['tool'],'capacity':c['chunk_capacity'],'retrieval_budget':config.get('retrieval_budget',512),'status':c['status'],'queries':summary.get('queries',x.get('queries','')),'recall':metric.get('recall',''),'precision':metric.get('precision',''),'iou':metric.get('iou',''),'vectors':c.get('chunks',c.get('passage_count','')),'native_passage_tokens':workload.get('passage_input_tokens',c.get('payload_tokens','')),'raw_tokens':c.get('raw_tokens',''),'derived_passages':c.get('derived_passages',''),'context_omitted':c.get('context_omitted',''),'chunk_seconds_median':c.get('chunk_seconds_median',''),'status_detail':c.get('detail','')})
for p in sorted(W.glob('*-lexical.json')):
 x=read(p);rel=p.name;inputs.append({'path':rel,'absolute_input':str(p),'sha256':H(p.read_bytes()),'bytes':p.stat().st_size})
 for c in x['rows']:
  rows.append({'artifact':rel,'artifact_sha256':H(p.read_bytes()),'corpus_id':c['corpus'],'retriever':x['model'],'stage':'lexical-screen-not-pretrained','tool':x['label'],'capacity':c['capacity'],'retrieval_budget':x['retrieval_budget'],'status':'ok','recall':c['recall'],'precision':c['precision'],'iou':c['iou'],'vectors':c['chunks'],'native_passage_tokens':c['native_tokens']})
fields=['artifact','artifact_sha256','corpus_id','manifest_sha256','runtime','model','model_revision','retriever','stage','tool','capacity','retrieval_budget','status','queries','recall','precision','iou','vectors','native_passage_tokens','raw_tokens','derived_passages','context_omitted','chunk_seconds_median','status_detail']
with (D/'development-outcomes.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(rows)
(D/'development-inputs.json').write_text(json.dumps({'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'DEVELOPMENT ONLY; no sealed validation data or results read','artifacts':inputs,'rows':len(rows),'csv_sha256':H((D/'development-outcomes.csv').read_bytes())},indent=2)+'\n')
print(json.dumps({'rows':len(rows),'artifacts':len(inputs),'csv_sha256':H((D/'development-outcomes.csv').read_bytes())}))
