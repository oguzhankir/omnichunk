"""Frozen supplementary development replay and repository-cluster comparisons."""
from pathlib import Path
import gzip,hashlib,json,os,subprocess,sys,time
from copy import deepcopy
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v2'
sys.path[:0]=[str(H/'src'),str(H)]
from benchmarks.compare_retrieval import compare_reports,load_report
TOOLS=['omnichunk','omnichunk-prose-compact','omnichunk-code-compact']
MODELS={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
CLUSTER=W/'code-files/development-repository-clusters.json'
clusters=json.loads(CLUSTER.read_text());assert len(set(clusters.values()))==15

def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def wait_for(path):
 deadline=time.monotonic()+7200
 while not path.exists():
  if 'Traceback (most recent call last)' in (W/'run-file-candidate-c1.log').read_text():raise RuntimeError('Primary candidate job failed; preserve its logs')
  if time.monotonic()>deadline:raise TimeoutError(str(path))
  time.sleep(10)

def replay(source,target,snapshot):
 if (target/'frontier.json').exists():
  d=json.loads((target/'frontier.json').read_text());assert d['source_report_file_sha256']==digest(source/'report.json.gz') and d['anchor_replay_exact'];return
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.with_suffix('.log').open('w') as f:
  subprocess.run([sys.executable,str(W/'frontier_frozen_c1.py'),'--report',str(source/'report.json.gz'),'--vectors',str(source/'vectors.json.gz'),'--model-dir',snapshot,'--output-dir',str(target),'--budgets','128','256','512'],cwd=H,env={**os.environ,'OMNICHUNK_FROZEN_HARNESS':str(H),'PYTHONPATH':str(H/'src'),'TOKENIZERS_PARALLELISM':'false','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'},stdout=f,stderr=subprocess.STDOUT,check=True)

def cache_audit(source,prior):
 original=json.load(gzip.open(prior/'vectors.json.gz'));new=json.load(gzip.open(source/'vectors.json.gz'))
 cache={(r['role'],r['text_sha256']):r['vector'] for r in original['records']};reused=missing=0;rows=[]
 for record in new['records']:
  key=record['role'],record['text_sha256']
  if key in cache:
   before=json.dumps(cache[key],allow_nan=False,separators=(',',':')).encode();after=json.dumps(record['vector'],allow_nan=False,separators=(',',':')).encode();assert before==after
   reused+=1;rows.append([*key,hashlib.sha256(before).hexdigest()])
  else:missing+=1
 metadata=new['producer_metadata'];stats=metadata['actual_encoder_work'];job=json.loads((source/'job.json').read_text())
 assert digest(prior/'vectors.json.gz')==job['cache_prior_sha256']==metadata['prior_artifact_sha256']
 assert sum(v['reused_texts'] for v in stats.values())==reused
 assert sum(v['new_texts'] for v in stats.values())==missing
 assert metadata['external_producer_source_sha256']==job['external_producer_sha256']
 for role,values in stats.items():assert sum(values['encoder_batch_sizes'])==values['new_texts'] and len(values['encoder_batch_sizes'])==values['encoder_calls']
 assert hashlib.sha256(json.dumps(sorted(rows),separators=(',',':')).encode()).hexdigest()==metadata['reused_vector_payloads_sha256']
 result={'prior_artifact_sha256':digest(prior/'vectors.json.gz'),'candidate_vectors_gzip_sha256':digest(source/'vectors.json.gz'),'candidate_required_records':len(new['records']),'reused_records_byte_exact':reused,'new_records':missing,'actual_encoder_work':stats,'candidate_workloads':metadata['candidate_workloads'],'maximum_input_tokens':metadata['maximum_input_tokens'],'max_sequence_length':metadata['max_sequence_length'],'script_sha256':metadata['external_producer_source_sha256'],'baseline_encoding_timings_not_copied':'timings' not in metadata}
 assert result['maximum_input_tokens']<=result['max_sequence_length']
 (source/'cache-audit.json').write_text(json.dumps(result,indent=2)+'\n')

def paired(bpath,cpath,out,baseline_tool,candidate_tool,capacity=None):
 baseline,bhash=load_report(bpath);candidate,chash=load_report(cpath)
 if capacity is not None:
  candidate=deepcopy(candidate);candidate['candidates']=[c for c in candidate['candidates'] if c['chunk_capacity']==capacity]
  candidate['configuration']['chunk_sizes']=[capacity]
  candidate['projection']={'input_report_sha256':chash,'capacity':capacity,'reason':'Baseline availability limited to this capacity; no inference, ranking or label changes'}
  projected=out.parent/f'candidate-{capacity}.projected.report.json'
  if not projected.exists():projected.write_text(json.dumps(candidate,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
  _,chash=load_report(projected)
 result=compare_reports(baseline,candidate,baseline_tool=baseline_tool,candidate_tool=candidate_tool,bootstrap_samples=2000,seed=0,cluster_map=clusters)
 result['reports']={'baseline_sha256':bhash,'candidate_sha256':chash}
 if out.exists():raise ValueError('Preserve prior paired output')
 out.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
 return result

summary=[]
for model,snapshot in MODELS.items():
 source=W/f'dev/code-files/{model}/candidate-final-c1';prior=W/f'dev/code-files/{model}/baseline'
 wait_for(source/'report.json.gz');wait_for(source/'vectors.json.gz')
 print(model,'cache audit and frozen frontier started',flush=True);cache_audit(source,prior)
 frontier=W/f'frontier/dev/code-files/{model}/candidate-final-c1';baseline=W/f'frontier/dev/code-files/{model}/baseline-frozen-c1'
 replay(source,frontier,snapshot)
 wait_for(baseline/'frontier.json')
 print(model,'exact512replay complete; paired comparisons started',flush=True)
 for budget in [128,256,512]:
  bpath=baseline/f'budget-{budget}.report.json';cpath=frontier/f'budget-{budget}.report.json'
  data,_=load_report(bpath);baseline_tools=list(dict.fromkeys(c['tool'] for c in data['candidates']))
  for tool in TOOLS:
   outdir=W/f'comparisons/dev/code-files/{model}/{budget}/{tool}';outdir.mkdir(parents=True,exist_ok=True)
   for reference in baseline_tools:
    result=paired(bpath,cpath,outdir/f'vs-{reference}.json',reference,tool)
    summary.append({'model':model,'budget':budget,'candidate':tool,'baseline':reference,'capacities':[c['chunk_capacity'] for c in result['comparisons']]})
   if model=='english':
    extra_source=W/'dev/code-files/english/chonkie-sentence-96';wait_for(extra_source/'report.json.gz')
    extra=W/'frontier/dev/code-files/english/chonkie-sentence-96-frozen-c1';wait_for(extra/'frontier.json')
    result=paired(extra/f'budget-{budget}.report.json',cpath,outdir/'vs-chonkie-sentence-96-only.json','chonkie-sentence',tool,96)
    summary.append({'model':model,'budget':budget,'candidate':tool,'baseline':'chonkie-sentence','capacities':[96],'availability':'96only;64failedconformance'})
 print(model,'paired comparisons complete',flush=True)
(W/'file-candidate-c1-postprocess-summary.json').write_text(json.dumps({'development_only':True,'supplemental_correlated_view':True,'repository_clusters':15,'bootstrap_samples':2000,'seed':0,'comparisons':summary},indent=2)+'\n')
print('all supplemental file DEV outputs complete',flush=True)
