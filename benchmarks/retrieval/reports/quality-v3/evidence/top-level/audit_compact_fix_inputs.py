import argparse,sys,json,hashlib,subprocess
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0,'/workspace/omnichunk')
from benchmarks.retrieval.adapters import split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
import omnichunk
p=argparse.ArgumentParser();p.add_argument('--runtime',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert str(Path(omnichunk.__file__).resolve()).startswith(str(Path(a.runtime).resolve()))
w=Path('/workspace/work/omnichunk-v3');root=Path('/workspace/omnichunk')
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
corpora={'code':w/'code/development','turkish':w/'turkish/development','synthetic':root/'benchmarks/retrieval/corpus_v1','squad-old':root/'benchmarks/retrieval/corpus_squad_v1'}
rows=[]
for model,path in models.items():
 counter=benchmark_counter('tokens',path,include_special_tokens=True)
 for label,corpus_path in corpora.items():
  corpus=load_corpus(corpus_path)
  docs=[d for d in corpus.documents if d.split=='dev']
  for capacity in [64,96]:
   passages=[asdict(p) for d in docs for p in split_document('omnichunk-code-compact',d.source_id,d.path,d.text,capacity,counter,'tokens')]
   payload=json.dumps(passages,ensure_ascii=False,separators=(',',':')).encode()
   rows.append({'model':model,'corpus':label,'capacity':capacity,'manifest_sha256':corpus.manifest_hash,'passage_count':len(passages),'native_tokens':sum(counter(p['text']) for p in passages),'passages_sha256':hashlib.sha256(payload).hexdigest(),'passages':passages})
a.output.write_text(json.dumps({'runtime':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.runtime,text=True).strip(),'rows':rows},indent=2,ensure_ascii=False)+'\n')
print('audited',len(rows),'development cells',flush=True)
