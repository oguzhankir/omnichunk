from __future__ import annotations
import hashlib,importlib.metadata,json,sys,time
from pathlib import Path
sys.path.insert(0,'/workspace/omnichunk')
from benchmarks.retrieval.adapters import split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
W=Path('/workspace/work/omnichunk-v3')
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
tools=['omnichunk','fixed','semchunk','langchain','langchain-code','semantic-text-splitter','semantic-code','llamaindex','llamaindex-sentence','chonkie-sentence']
cases=[('code-files',W/'code-files/development',tools,['multilingual','english']),('code',W/'code/development',['semantic-code'],['multilingual','english']),('turkish',W/'turkish/development',['semantic-code'],['multilingual'])]
out={}
for name,path,selected,model_names in cases:
 corpus=load_corpus(path)
 for model in model_names:
  counter=benchmark_counter('tokens',models[model],include_special_tokens=True)
  for tool in selected:
   for capacity in [64,96]:
    rows=[]
    for doc in corpus.documents:
     if doc.split!='dev':continue
     try:
      started=time.perf_counter();passages=split_document(tool,doc.source_id,doc.path,doc.text,capacity,counter,'tokens')
      rows.append({'source_id':doc.source_id,'status':'ok','passages':len(passages),'native_tokens':sum(counter(p.text) for p in passages),'seconds':time.perf_counter()-started})
     except Exception as exc:
      rows.append({'source_id':doc.source_id,'status':type(exc).__name__,'error':str(exc)})
    key=f'{name}-{model}-{tool}-{capacity}'
    out[key]={'corpus_manifest_sha256':corpus.manifest_hash,'documents':len(rows),'valid':sum(r['status']=='ok' for r in rows),'rows':rows}
    print(key,len(rows),out[key]['valid'],flush=True)
    (W/'adapter-audit/fullfile-development-conformance.json').write_text(json.dumps(out,indent=2)+'\n')
(W/'adapter-audit/fullfile-conformance-provenance.json').write_text(json.dumps({'scope':'Development conformance only, no query scores; all requested cells retained','models':models,'tools':tools,'packages':{n:importlib.metadata.version(n) for n in ['semantic-text-splitter','tree-sitter-python','langchain-text-splitters','llama-index-core','chonkie']},'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
