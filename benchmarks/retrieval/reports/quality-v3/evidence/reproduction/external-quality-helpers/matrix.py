"""Explicit corpus/runtime/encoder cell using unchanged benchmark commands."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/workspace/omnichunk')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--checkout', type=Path, required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--split', choices=['dev','test'], default='dev')
    p.add_argument('--model-dir', type=Path, required=True)
    p.add_argument('--model-id', required=True)
    p.add_argument('--model-sha', required=True)
    p.add_argument('--tools', default='omnichunk,fixed,semchunk,langchain,semantic-text-splitter,llamaindex')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists(), 'Never replace an experiment'
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=a.checkout,text=True).strip()
    a.output.mkdir(parents=True)
    env={**os.environ,'PYTHONPATH':str(a.checkout.resolve()/'src'),'OMP_NUM_THREADS':'2',
         'MKL_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','PYTHONHASHSEED':'0',
         'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HOME':'/workspace/work/cache/huggingface',
         'XDG_CACHE_HOME':'/workspace/work/cache'}
    common=['--corpus',str(a.corpus.resolve()),'--split',a.split,'--tools',a.tools,
            '--chunk-sizes','64','96','--unit','tokens','--tokenizer',str(a.model_dir.resolve()),
            '--include-special-tokens']
    def run(cmd,log):
        with (a.output/log).open('w') as f:
            subprocess.run([sys.executable,*cmd],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    run(['benchmarks/prepare_dense.py',*common,'--model-dir',str(a.model_dir.resolve()),
         '--model-id',a.model_id,'--model-revision',a.model_sha,'--batch-size','32',
         '--cpu-threads','2','--output',str(a.output/'vectors.json')],'prepare.log')
    run(['benchmarks/run_retrieval.py',*common,'--retriever','dense','--dense-embeddings',
         str(a.output/'vectors.json'),'--retrieval-budget','512','--top-k','5','--repeats','3',
         '--require-all','--output',str(a.output/'report.json')],'evaluate.log')
    d=json.loads((a.output/'report.json').read_text())
    assert all(r['status']=='ok' for r in d['candidates'])
    for name in ('vectors.json','report.json'):
        with (a.output/name).open('rb') as f,(a.output/(name+'.gz')).open('wb') as raw:
            with gzip.GzipFile(fileobj=raw,filename='',mtime=0,mode='wb') as z:
                shutil.copyfileobj(f,z)
        (a.output/name).unlink()
    print(json.dumps({'output':str(a.output),'revision':d['environment']['runtime_git_revision'],
                      'rows':len(d['candidates']),'queries':d['queries']}))


if __name__=='__main__':
    main()
