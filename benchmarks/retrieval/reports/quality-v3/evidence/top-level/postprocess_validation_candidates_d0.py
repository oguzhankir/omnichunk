"""Frozen supplementary development replay and repository-cluster comparisons."""
from pathlib import Path
import gzip,hashlib,json,os,subprocess,sys,time
from copy import deepcopy
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v3'
sys.path[:0]=[str(H/'src'),str(H)]
from benchmarks.compare_retrieval import compare_reports,load_report
TOOLS=['omnichunk','omnichunk-prose-compact','omnichunk-code-compact']
MODELS={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
clusters=None

def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def wait_for(path):
 deadline=time.monotonic()+7200
 while not path.exists() or (path.suffix=='.gz' and path.with_suffix('').exists()):
  if 'Traceback (most recent call last)' in (W/'validation-candidates-d0.log').read_text():raise RuntimeError('Primary candidate job failed; preserve its logs')
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
 assert digest(prior/'vectors.json.gz')==job['prior_artifact_sha256']==metadata['prior_artifact_sha256']
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


V=W/'validation'
CASES=[('code','english'),('turkish','multilingual'),('code','multilingual'),('code-files','multilingual'),('code-files','english')]
summary=[]
for domain,model in CASES:
    snapshot=MODELS[model]
    case=V/domain if domain=='turkish' else V/domain/model
    source=case/'candidate-final-d0';prior=case/'baseline'
    wait_for(source/'report.json.gz');wait_for(source/'vectors.json.gz')
    print(domain,model,'cache audit and frozen frontier started',flush=True)
    cache_audit(source,prior)
    data=json.loads((W/domain/'validation/manifest.json').read_text())
    gold={span['source_id'] for query in data['queries'] if query['split']=='test' for span in query['evidence']}
    if domain=='turkish':
        clusters=None
        assert len(gold)==60
    else:
        clusters={doc['source_id']:doc['repository'] for doc in data['documents'] if doc['source_id'] in gold}
        assert set(clusters)==gold and len(set(clusters.values()))==16
        (case/'repository-clusters.json').write_text(json.dumps(clusters,sort_keys=True,indent=2)+'\n')
    basefront=W/'frontier/validation'/domain if domain=='turkish' else W/'frontier/validation'/domain/model
    frontier=basefront/'candidate-final-d0';replay(source,frontier,snapshot)
    while True:
        events=[]
        for line in (V/'baseline-events.jsonl').read_text().splitlines():
            try:events.append(json.loads(line))
            except json.JSONDecodeError:pass
        if any(e['event']=='domain-completed' and e['domain']==domain and e['model']==model for e in events):break
        time.sleep(10)
    groups=[p for p in sorted(case.glob('baseline*')) if p.is_dir() and (p/'report.json.gz').exists()]
    assert prior in groups
    for group in groups:
        replay(group,basefront/group.name,snapshot)
    print(domain,model,'all512anchorsverified; paired comparisons started',flush=True)
    for budget in [128,256,512]:
        cpath=frontier/f'budget-{budget}.report.json'
        for group in groups:
            bpath=basefront/group.name/f'budget-{budget}.report.json'
            baseline,_=load_report(bpath)
            references=list(dict.fromkeys(c['tool'] for c in baseline['candidates']))
            for reference in references:
                capacities=sorted({c['chunk_capacity'] for c in baseline['candidates'] if c['tool']==reference})
                assert capacities in [[64,96],[64],[96]]
                projection=None if len(capacities)==2 else capacities[0]
                suffix='' if projection is None else f'-{projection}-only'
                for tool in TOOLS:
                    outdir=W/'comparisons/validation'/domain/str(budget)/tool if domain=='turkish' else W/'comparisons/validation'/domain/model/str(budget)/tool
                    outdir.mkdir(parents=True,exist_ok=True)
                    result=paired(bpath,cpath,outdir/f'vs-{reference}{suffix}.json',reference,tool,projection)
                    expected=60 if domain=='turkish' else 16
                    assert all(c['slices']['all']['gold_source_clusters']==expected for c in result['comparisons'])
                    summary.append({'domain':domain,'model':model,'budget':budget,'candidate':tool,'baseline':reference,'baseline_group':group.name,'capacities':capacities,'clusters':expected})
    (case/'candidate-postprocess-complete.json').write_text(json.dumps({'status':'ok','freeze':'54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334','comparisons':[s for s in summary if s['domain']==domain and s['model']==model]},indent=2)+'\n')
    print(domain,model,'all frozen frontiers and paired comparisons complete',flush=True)
(V/'candidate-postprocess-summary.json').write_text(json.dumps({'validation_only':True,'no_post_release_tuning':True,'bootstrap_samples':2000,'seed':0,'comparisons':summary},indent=2)+'\n')
print('all validation candidate postprocessing complete',flush=True)
