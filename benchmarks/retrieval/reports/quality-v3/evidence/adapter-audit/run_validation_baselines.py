from __future__ import annotations
import concurrent.futures,gzip,hashlib,json,os,shutil,subprocess,sys,threading,time
from pathlib import Path
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v3';B=W/'baseline';O=W/'validation';O.mkdir(exist_ok=True)
F=W/'freeze-before-validation-v3.json';F_SHA='54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334';assert hashlib.sha256(F.read_bytes()).hexdigest()==F_SHA
freeze=json.loads(F.read_text())
for name,sha in freeze['harness_files'].items():assert hashlib.sha256((H/name).read_bytes()).hexdigest()==sha
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=B,text=True).strip()=='e63c7f097a8ccec39262c8fb00fb2375a3e5283d'
assert not subprocess.check_output(['git','status','--porcelain'],cwd=B,text=True).strip()
TOOLS=['omnichunk','fixed','semchunk','langchain','semantic-text-splitter','llamaindex','chonkie-sentence','langchain-code','llamaindex-sentence','semantic-code']
models={'multilingual':(Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','e8f8c211226b894fcb81acc59f3b34ba3efd5f42'),'english':(Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip(),'sentence-transformers/all-MiniLM-L6-v2','1110a243fdf4706b3f48f1d95db1a4f5529b4d41')}
lock=threading.Lock()
def event(kind,**values):
 record={'event':kind,'time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**values}
 with lock:
  with (O/'baseline-events.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
  print(json.dumps(record),flush=True)
def compress(p):
 with p.open('rb') as a,p.with_suffix(p.suffix+'.gz').open('wb') as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as z:shutil.copyfileobj(a,z)
 p.unlink()
def run(domain,model):
 corpus=W/domain/'validation';manifest=corpus/'manifest.json'
 expected=freeze['validation_commitments'][domain].get('validation_manifest_sha256',freeze['validation_commitments'][domain].get('manifest_sha256'))
 assert hashlib.sha256(manifest.read_bytes()).hexdigest()==expected
 base=O/domain if domain=='turkish' else O/domain/model
 base.mkdir(parents=True,exist_ok=False)
 snapshot,model_id,revision=models[model]
 env={**os.environ,'PYTHONPATH':str(B/'src'),'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','PYTHONHASHSEED':'0','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','NLTK_DATA':str(W/'adapter-audit/nltk_data')}
 def command(args,log,expected_exit=0):
  with log.open('w') as f:r=subprocess.run([sys.executable,*args],cwd=H,env=env,stdout=f,stderr=subprocess.STDOUT)
  if r.returncode!=expected_exit:raise RuntimeError(f'{log} exit{r.returncode} expected{expected_exit}')
 event('preflight-start',domain=domain,model=model,manifest_sha256=expected)
 command([str(W/'adapter-audit/validation_preflight.py'),'--corpus',str(corpus),'--tokenizer',snapshot,'--output',str(base/'preflight.json')],base/'preflight.log')
 audit=json.loads((base/'preflight.json').read_text())['cells']
 success=lambda tool,cap:audit[f'{tool}-{cap}']['valid']==audit[f'{tool}-{cap}']['documents']
 common=[tool for tool in TOOLS if all(success(tool,cap) for cap in [64,96])]
 groups=[('baseline',common,[64,96])]
 for cap in [64,96]:
  partial=[tool for tool in TOOLS if tool not in common and success(tool,cap)]
  if partial:groups.append((f'baseline-valid-{cap}',partial,[cap]))
 failed=[{'tool':tool,'capacity':cap,'failed_source_ids':[r['source_id'] for r in audit[f'{tool}-{cap}']['rows'] if r['status']!='ok']} for tool in TOOLS for cap in [64,96] if not success(tool,cap)]
 (base/'conformance-groups.json').write_text(json.dumps({'freeze_sha256':F_SHA,'groups':groups,'failures':failed,'policy':'Strict source/budget conformance grouping only; all failed cells retained,no output repair,no per-file filtering,no qualityscore selection'},indent=2)+'\n')
 event('preflight-completed',domain=domain,model=model,groups=groups,failures=failed)
 for label,tools,caps in groups:
  if not tools:continue
  out=base/label;out.mkdir()
  settings=['--corpus',str(corpus),'--split','test','--tools',','.join(tools),'--chunk-sizes',*[str(c) for c in caps],'--unit','tokens','--tokenizer',snapshot,'--include-special-tokens']
  (out/'job.json').write_text(json.dumps({'freeze_sha256':F_SHA,'runtime':'e63c7f097a8ccec39262c8fb00fb2375a3e5283d','harness_commit':freeze['runtime_and_harness_commit'],'domain':domain,'model':model_id,'revision':revision,'corpus_manifest_sha256':expected,'tools':tools,'capacities':caps,'context':'none','overlap':0,'primary_retrieval_budget':512,'sensitivity_budgets':[128,256],'top_k':5,'repeats':3,'batch_size':32,'Torch_threads':2,'Torch_interop_threads':2},indent=2)+'\n')
  event('preparation-start',domain=domain,model=model,group=label,tools=tools,capacities=caps)
  command(['benchmarks/prepare_dense.py',*settings,'--model-dir',snapshot,'--model-id',model_id,'--model-revision',revision,'--batch-size','32','--cpu-threads','2','--output',str(out/'vectors.json')],out/'prepare.log')
  event('vectors-ready',domain=domain,model=model,group=label,directory=str(out),vectors=str(out/'vectors.json'))
  command(['benchmarks/run_retrieval.py',*settings,'--retriever','dense','--dense-embeddings',str(out/'vectors.json'),'--retrieval-budget','512','--top-k','5','--repeats','3','--require-all','--output',str(out/'report.json')],out/'evaluate.log')
  r=json.loads((out/'report.json').read_text());assert all(c['status']=='ok' for c in r['candidates'])
  event('report-ready',domain=domain,model=model,group=label,directory=str(out),queries=r['queries'],cells=len(r['candidates']))
  for name in ['vectors.json','report.json']:compress(out/name)
  event('group-completed',domain=domain,model=model,group=label,directory=str(out))
 for failure in failed:
  tool,cap=failure['tool'],failure['capacity'];out=base/'failures'/f'{tool}-{cap}';out.mkdir(parents=True)
  command(['benchmarks/run_retrieval.py','--corpus',str(corpus),'--split','test','--tools',tool,'--chunk-sizes',str(cap),'--unit','tokens','--tokenizer',snapshot,'--include-special-tokens','--retrieval-budget','512','--top-k','5','--repeats','1','--require-all','--output',str(out/'report.json')],out/'source-conformance.log',expected_exit=1)
  r=json.loads((out/'report.json').read_text());assert all(c['status']!='ok' for c in r['candidates'])
  (out/'scope.json').write_text(json.dumps({'purpose':'Frozen validation source/budget conformance failure only; no successful retrievalaggregate; no inference','freeze_sha256':F_SHA,**failure},indent=2)+'\n')
 event('domain-completed',domain=domain,model=model,directory=str(base))
 return str(base)
jobs=[('turkish','multilingual'),('code','english'),('code-files','multilingual'),('code','multilingual'),('code-files','english')]
(O/'baseline-controller.json').write_text(json.dumps({'freeze_sha256':F_SHA,'max_workers':2,'jobs':jobs,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'settings':'Fixed per freeze; native conformance failures retained; no tuning'},indent=2)+'\n')
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 futures={pool.submit(run,*job):job for job in jobs}
 for future in concurrent.futures.as_completed(futures):
  try:print('DONE',future.result(),flush=True)
  except Exception as exc:event('CONTROLLER-ERROR',job=futures[future],error=repr(exc));raise
for name,sha in freeze['harness_files'].items():assert hashlib.sha256((H/name).read_bytes()).hexdigest()==sha
event('ALL-BASELINES-COMPLETED')
