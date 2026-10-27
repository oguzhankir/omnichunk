from __future__ import annotations
import argparse,hashlib,json,sys,time
from pathlib import Path
H=Path('/workspace/work/omnichunk-v3/frozen-candidate-v3');sys.path.insert(0,str(H))
from benchmarks.retrieval.adapters import split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,required=True);p.add_argument('--tokenizer',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
corpus=load_corpus(a.corpus);assert all(d.split=='test' for d in corpus.documents)
count=benchmark_counter('tokens',a.tokenizer,include_special_tokens=True)
tools=['omnichunk','fixed','semchunk','langchain','semantic-text-splitter','llamaindex','chonkie-sentence','langchain-code','llamaindex-sentence','semantic-code'];out={}
for tool in tools:
 for cap in [64,96]:
  rows=[]
  for doc in corpus.documents:
   started=time.perf_counter()
   try:
    chunks=split_document(tool,doc.source_id,doc.path,doc.text,cap,count,'tokens')
    rows.append({'source_id':doc.source_id,'status':'ok','passages':len(chunks),'native_tokens':sum(count(x.text) for x in chunks),'seconds':time.perf_counter()-started})
   except Exception as e:rows.append({'source_id':doc.source_id,'status':type(e).__name__,'error':str(e)})
  out[f'{tool}-{cap}']={'tool':tool,'capacity':cap,'documents':len(rows),'valid':sum(r['status']=='ok' for r in rows),'rows':rows}
  a.output.write_text(json.dumps({'scope':'FROZEN VALIDATION source/budget conformance only; NO retrieval-score selection','corpus_manifest_sha256':corpus.manifest_hash,'cells':out},indent=2)+'\n')
  print(tool,cap,out[f'{tool}-{cap}']['valid'],'/',len(rows),flush=True)
