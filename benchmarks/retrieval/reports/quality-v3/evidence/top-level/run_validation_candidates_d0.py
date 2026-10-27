"""One external validation candidate worker under the released, immutable v3 freeze."""
from pathlib import Path
import fcntl,gzip,hashlib,json,os,subprocess,sys,time
from datetime import datetime,timezone
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v3';V=W/'validation'
FREEZE_SHA='54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334'
FROZEN='d0bd4b5ea10ff458313a82b3340c8f1a3f49e572'
TOOLS='omnichunk,omnichunk-prose-compact,omnichunk-code-compact'
MODELS={'multilingual':(Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','e8f8c211226b894fcb81acc59f3b34ba3efd5f42'),'english':(Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip(),'sentence-transformers/all-MiniLM-L6-v2','1110a243fdf4706b3f48f1d95db1a4f5529b4d41')}
CASES=[('code','english'),('turkish','multilingual'),('code','multilingual'),('code-files','multilingual'),('code-files','english')]
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def event(name,**fields):
 row={'event':name,'time_utc':datetime.now(timezone.utc).isoformat(),**fields}
 with (V/'candidate-events.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 print(json.dumps(row),flush=True)
def target(domain,model):return V/domain/('baseline' if domain=='turkish' else model+'/baseline')
def complete(path):return path.exists() and not path.with_suffix('').exists()
def baseline_active():
 active=set();path=V/'baseline-events.jsonl'
 if not path.exists():return 0
 for line in path.read_text().splitlines():
  try:r=json.loads(line)
  except json.JSONDecodeError:continue
  key=(r.get('domain'),r.get('model'),r.get('group'))
  if r['event']=='preparation-start':active.add(key)
  elif r['event']=='vectors-ready':active.discard(key)
 return len(active)
def encoder_slot():
 slots=W/'encoder-slots';slots.mkdir(exist_ok=True)
 while True:
  if baseline_active()<2:
   for n in [0,1]:
    f=(slots/f'{n}.lock').open('a+')
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return f,n
    except BlockingIOError:f.close()
  time.sleep(5)
def run(args,out,log,env):
 with (out/log).open('w') as f:subprocess.run([sys.executable,*args],cwd=H,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
def compress(p):
 tmp=p.with_suffix(p.suffix+'.gz.partial');dst=p.with_suffix(p.suffix+'.gz')
 with p.open('rb') as src,tmp.open('wb') as raw,gzip.GzipFile(fileobj=raw,filename='',mtime=0,mode='wb') as gz:
  import shutil
  shutil.copyfileobj(src,gz)
 os.link(tmp,dst);tmp.unlink();p.unlink()
assert digest(W/'freeze-before-validation-v3.json')==FREEZE_SHA
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=H,text=True).strip()==FROZEN
assert not subprocess.check_output(['git','status','--porcelain'],cwd=H,text=True).strip()
freeze=json.loads((W/'freeze-before-validation-v3.json').read_text())
for path,sha in freeze['runtime_files'].items():assert digest(H/'src/omnichunk'/path)==sha
V.mkdir(exist_ok=True)
worker=(V/'candidate-controller.lock').open('a+');fcntl.flock(worker,fcntl.LOCK_EX|fcntl.LOCK_NB)
(V/'candidate-controller.json').write_text(json.dumps({'freeze_sha256':FREEZE_SHA,'runtime':FROZEN,'cases':CASES,'max_candidate_workers':1,'script_sha256':digest(Path(__file__)),'external_producer_sha256':digest(W/'extend_dense_vectors.py'),'settings':'All three frozen profiles; native64/96; no post-release selection or repair','resource_scope':'Two shared advisory encoder slots plus best-effort baseline-event gating; model pools2, quotaCPU4/RAM16; timings not isolated'},indent=2)+'\n')
for domain,model in CASES:
 prior=target(domain,model);corpus=W/domain/'validation';out=prior.parent/'candidate-final-d0'
 event('waiting-baseline',domain=domain,model=model,directory=str(prior))
 while not (complete(prior/'vectors.json.gz') and complete(prior/'report.json.gz')):time.sleep(10)
 out.mkdir();snapshot,model_id,revision=MODELS[model];vectors=out/'vectors.json';report=out/'report.json'
 env={**os.environ,'PYTHONPATH':str(H/'src'),'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','PYTHONHASHSEED':'0','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','NLTK_DATA':str(W/'adapter-audit/nltk_data')}
 job={'split':'test','domain':domain,'model':model_id,'model_revision':revision,'runtime':FROZEN,'freeze_sha256':FREEZE_SHA,'tools':TOOLS,'native_chunk_capacities':[64,96],'primary_context_budget':512,'corpus_manifest_sha256':digest(corpus/'manifest.json'),'prior_artifact':str(prior/'vectors.json.gz'),'prior_artifact_sha256':digest(prior/'vectors.json.gz'),'external_producer_sha256':digest(W/'extend_dense_vectors.py')}
 (out/'job.json').write_text(json.dumps(job,indent=2)+'\n')
 try:
  slot,n=encoder_slot();event('preparation-start',domain=domain,model=model,slot=n)
  try:run([str(W/'extend_dense_vectors.py'),'--harness-root',str(H),'--runtime-root',str(H),'--corpus',str(corpus),'--model-dir',snapshot,'--model-id',model_id,'--model-revision',revision,'--prior',str(prior/'vectors.json.gz'),'--prior-sha256',job['prior_artifact_sha256'],'--split','test','--tools',TOOLS,'--chunk-sizes','64','96','--batch-size','32','--cpu-threads','2','--output',str(vectors)],out,'prepare.log',env)
  finally:fcntl.flock(slot,fcntl.LOCK_UN);slot.close()
  event('preparation-complete',domain=domain,model=model)
  run([str(H/'benchmarks/run_retrieval.py'),'--corpus',str(corpus),'--split','test','--tools',TOOLS,'--chunk-sizes','64','96','--unit','tokens','--tokenizer',snapshot,'--include-special-tokens','--retriever','dense','--dense-embeddings',str(vectors),'--retrieval-budget','512','--top-k','5','--repeats','3','--require-all','--output',str(report)],out,'evaluate.log',env)
  d=json.loads(report.read_text());assert d['environment']['runtime_git_revision']==FROZEN and not d['environment']['runtime_git_dirty'];assert all(c['status']=='ok' for c in d['candidates'])
  for p in [vectors,report]:compress(p)
  (out/'status.json').write_text(json.dumps({'status':'ok','report_gzip_sha256':digest(out/'report.json.gz'),'vectors_gzip_sha256':digest(out/'vectors.json.gz')},indent=2)+'\n')
  event('candidate-complete',domain=domain,model=model,directory=str(out))
 except Exception as exc:
  (out/'status.json').write_text(json.dumps({'status':'error','error':str(exc),'policy':'No frozen source/settings changed; retain failure and notify root'},indent=2)+'\n');event('candidate-error',domain=domain,model=model,error=str(exc));raise
(V/'candidate-completed.json').write_text(json.dumps({'status':'ok','cases':CASES,'freeze_sha256':FREEZE_SHA},indent=2)+'\n')
event('all-candidates-complete')
