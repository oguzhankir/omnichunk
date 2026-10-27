"""DEV input-only audit of Python routing; no model inference or validation reads."""
import argparse,hashlib,inspect,json
from dataclasses import asdict
from pathlib import Path
import omnichunk
from omnichunk.util import detect
from benchmarks.retrieval.adapters import split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
result={'runtime_module':omnichunk.__file__,'detect_function_sha256':hashlib.sha256(inspect.getsource(detect._looks_hybrid_python).encode()).hexdigest(),'cells':[]}
for model,path in models.items():
 counter=benchmark_counter('tokens',path,include_special_tokens=True)
 for domain in ('code','turkish'):
  corpus=load_corpus(Path('/workspace/work/omnichunk-v3')/domain/'development');assert all(d.split=='dev'for d in corpus.documents)
  for cap in (64,96):
   for tool in ('omnichunk','omnichunk-prose-compact','omnichunk-code-compact'):
    rows=[asdict(x)for d in corpus.documents for x in split_document(tool,d.source_id,d.path,d.text,cap,counter,'tokens')]
    result['cells'].append({'model':model,'domain':domain,'capacity':cap,'tool':tool,'manifest_sha256':corpus.manifest_hash,'passages':rows})
a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('cells',len(result['cells']))
