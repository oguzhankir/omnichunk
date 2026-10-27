from __future__ import annotations
import gzip,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
sys.path.insert(0,'/workspace/work/omnichunk-v3')
from run_jobs import job,MODELS,RIVALS
W=Path('/workspace/work/omnichunk-v3');ROOT=Path('/workspace/omnichunk')
AUDIT=json.loads((W/'adapter-audit/fullfile-development-conformance.json').read_text())
tools=RIVALS+',semantic-code'
for model in MODELS:
 selected=tools.split(',')
 failed={tool:[capacity for capacity in [64,96] if AUDIT[f'code-files-{model}-{tool}-{capacity}']['valid']!=AUDIT[f'code-files-{model}-{tool}-{capacity}']['documents']] for tool in selected}
 complete=[tool for tool in selected if not failed[tool]]
 print('JOB fullfile',model,complete,'failurecells',failed,flush=True)
 job(W/'baseline',W/'code-files/development',model,','.join(complete),W/f'dev/code-files/{model}/baseline')
 if model=='english':
  # Preserve Chonkie's valid96 cell separately;64 was rejected before inference.
  out=W/'dev/code-files/english/chonkie-sentence-96';out.mkdir(parents=True)
  snapshot,model_id,revision=MODELS[model]
  env={**os.environ,'PYTHONPATH':str(W/'baseline/src'),'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','PYTHONHASHSEED':'0','HF_HUB_OFFLINE':'1','NLTK_DATA':str(W/'adapter-audit/nltk_data')}
  common=['--corpus',str(W/'code-files/development'),'--split','dev','--tools','chonkie-sentence','--chunk-sizes','96','--unit','tokens','--tokenizer',snapshot,'--include-special-tokens']
  def command(arguments,log):
   with (out/log).open('w') as f:subprocess.run([sys.executable,*arguments],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
  command(['benchmarks/prepare_dense.py',*common,'--model-dir',snapshot,'--model-id',model_id,'--model-revision',revision,'--batch-size','32','--cpu-threads','2','--output',str(out/'vectors.json')],'prepare.log')
  command(['benchmarks/run_retrieval.py',*common,'--retriever','dense','--dense-embeddings',str(out/'vectors.json'),'--retrieval-budget','512','--top-k','5','--repeats','3','--require-all','--output',str(out/'report.json')],'evaluate.log')
  for name in ['vectors.json','report.json']:
   p=out/name
   with p.open('rb') as f,p.with_suffix(p.suffix+'.gz').open('wb') as raw,gzip.GzipFile(fileobj=raw,filename='',mtime=0) as z:shutil.copyfileobj(f,z)
   p.unlink()
  (out/'job.json').write_text(json.dumps({'capacity':96,'strategy':'chonkie-sentence','capacity64':'FAILED PREFLIGHT; no successful aggregate','runtime':'e63c7f0','corpus_manifest_sha256':hashlib.sha256((W/'code-files/development/manifest.json').read_bytes()).hexdigest()},indent=2)+'\n')
for model in MODELS:
 print('JOB isolatedsemantic',model,flush=True)
 job(W/'baseline',W/'code/development',model,'semantic-code',W/f'dev/code/{model}/semantic-code')
print('JOB turkishsemantic',flush=True)
job(W/'baseline',W/'turkish/development','multilingual','semantic-code',W/'dev/turkish/semantic-code')
print('DONE ALL BASELINES',flush=True)
