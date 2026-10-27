import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/workspace/omnichunk')
WORK = Path('/workspace/work/omnichunk-v3')
MULTI = Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip()
ENGLISH = Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()
MODELS = {'multilingual': (MULTI, 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'), 'english': (ENGLISH, 'sentence-transformers/all-MiniLM-L6-v2', '1110a243fdf4706b3f48f1d95db1a4f5529b4d41')}
RIVALS = 'omnichunk,fixed,semchunk,langchain,semantic-text-splitter,llamaindex,chonkie-sentence,langchain-code,llamaindex-sentence'

def compress(path):
    with path.open('rb') as source, path.with_suffix(path.suffix+'.gz').open('wb') as raw, gzip.GzipFile(fileobj=raw, filename='', mtime=0, mode='wb') as target:
        shutil.copyfileobj(source, target)
    path.unlink()

def job(checkout, corpus, model, tools, output, existing_vectors=False):
    snapshot, model_id, revision = MODELS[model]
    checkout=Path(checkout);corpus=Path(corpus);output=Path(output)
    if subprocess.check_output(['git','status','--porcelain'],cwd=checkout,text=True).strip():
        raise ValueError('Runtime checkout must be clean')
    output.mkdir(parents=True,exist_ok=existing_vectors)
    vectors=output/'vectors.json';report=output/'report.json'
    if report.exists() or report.with_suffix('.json.gz').exists():raise ValueError('Preserve existing report')
    env={**os.environ,'PYTHONPATH':str(checkout/'src'),'OMP_NUM_THREADS':'2','MKL_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','PYTHONHASHSEED':'0','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','NLTK_DATA':str(WORK/'adapter-audit/nltk_data')}
    common=['--corpus',str(corpus),'--split','dev','--tools',tools,'--chunk-sizes','64','96','--unit','tokens','--tokenizer',snapshot,'--include-special-tokens']
    manifest={'runtime':subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip(),'corpus_sha256':hashlib.sha256((corpus/'manifest.json').read_bytes()).hexdigest(),'model':model_id,'revision':revision,'tools':tools,'native_chunk_capacities':[64,96],'primary_context_budget':512,'split':'dev','existing_vectors':existing_vectors}
    (output/'job.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def command(args,log):
        with (output/log).open('w') as f:subprocess.run([sys.executable,*args],cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    if existing_vectors:
        if not vectors.exists():raise ValueError('Missing prepared vectors')
        if (output/'evaluate.log').exists():(output/'evaluate.log').rename(output/'cli-rejected-evaluate.log')
    else:
        command(['benchmarks/prepare_dense.py',*common,'--model-dir',snapshot,'--model-id',model_id,'--model-revision',revision,'--batch-size','32','--cpu-threads','2','--output',str(vectors)],'prepare.log')
    command(['benchmarks/run_retrieval.py',*common,'--retriever','dense','--dense-embeddings',str(vectors),'--retrieval-budget','512','--top-k','5','--repeats','3','--require-all','--output',str(report)],'evaluate.log')
    d=json.loads(report.read_text());assert all(c['status']=='ok' for c in d['candidates'])
    print(json.dumps({'output':str(output),'queries':d['queries'],'runtime':manifest['runtime']}),flush=True)
    for path in [vectors,report]:compress(path)

if __name__=='__main__':
    selected=sys.argv[1]
    if selected=='resume':
        job(WORK/'variant-packing',ROOT/'benchmarks/retrieval/corpus_v1','multilingual','omnichunk,omnichunk-pack',WORK/'dev/synthetic/packing',True)
        job(WORK/'baseline',WORK/'turkish/development','multilingual',RIVALS,WORK/'dev/turkish/baseline',True)
    elif selected=='code':
        for model in MODELS:job(WORK/'baseline',WORK/'code/development',model,RIVALS,WORK/f'dev/code/{model}/baseline-summary')
    elif selected=='combined-synthetic':
        job(ROOT,ROOT/'benchmarks/retrieval/corpus_v1','multilingual','omnichunk,omnichunk-pack',WORK/'dev/synthetic/combined')
