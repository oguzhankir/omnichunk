"""Input-only development whole-file audit; no model inference or metric reads."""
import argparse,hashlib,json,subprocess
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import sys
sys.path.insert(0,'/workspace/omnichunk')
from benchmarks.retrieval.adapters import split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
import omnichunk
from omnichunk.util.detect import detect_content_type,detect_language
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert Path(omnichunk.__file__).resolve().is_relative_to(a.runtime.resolve())
w=Path('/workspace/work/omnichunk-v3');corpus=load_corpus(w/'code-files/development');docs=[d for d in corpus.documents if d.split=='dev'];assert len(docs)==len(corpus.documents)==37
classifications=[{'source_id':d.source_id,'path':d.path,'language':detect_language(d.path,d.text),'content_type':detect_content_type(d.path,d.text).value,'source_utf8_bytes':len(d.text.encode())}for d in docs]
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
rows=[]
for model,path in models.items():
 counter=benchmark_counter('tokens',path,include_special_tokens=True)
 for capacity in (64,96):
  for tool in ('omnichunk','omnichunk-prose-compact','omnichunk-code-compact'):
   passages=[asdict(p)for d in docs for p in split_document(tool,d.source_id,d.path,d.text,capacity,counter,'tokens')]
   raw=json.dumps(passages,ensure_ascii=False,separators=(',',':')).encode()
   row={'tool':tool,'model':model,'corpus':'code-files','capacity':capacity,'manifest_sha256':corpus.manifest_hash,'passage_count':len(passages),'native_tokens':sum(counter(p['text'])for p in passages),'passages_sha256':hashlib.sha256(raw).hexdigest(),'passages':passages};rows.append(row)
   print(model,capacity,tool,'passages',len(passages),flush=True)
result={'runtime':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.runtime,text=True).strip(),'classification_counts':dict(Counter(d['content_type']for d in classifications)),'language_counts':dict(Counter(d['language']for d in classifications)),'classifications':classifications,'rows':rows}
a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print('classification_counts',result['classification_counts'],flush=True)
