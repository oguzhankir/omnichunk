from pathlib import Path
import subprocess,sys,os
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v2'
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
for model,snapshot in models.items():
 for label in ['baseline']+(['chonkie-sentence-96'] if model=='english' else []):
  source=W/f'dev/code-files/{model}/{label}';target=W/f'frontier/dev/code-files/{model}/{label}-frozen-c1'
  target.parent.mkdir(parents=True,exist_ok=True)
  print(model,label,'frontier started',flush=True)
  with target.with_suffix('.log').open('w') as f:
   subprocess.run([sys.executable,str(W/'frontier_frozen_c1.py'),'--report',str(source/'report.json.gz'),'--vectors',str(source/'vectors.json.gz'),'--model-dir',snapshot,'--output-dir',str(target),'--budgets','128','256','512'],cwd=H,env={**os.environ,'OMNICHUNK_FROZEN_HARNESS':str(H),'PYTHONPATH':str(H/'src'),'TOKENIZERS_PARALLELISM':'false','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'},stdout=f,stderr=subprocess.STDOUT,check=True)
  print(model,label,'frontier complete',flush=True)
