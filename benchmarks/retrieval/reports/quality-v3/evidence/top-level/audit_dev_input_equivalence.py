"""Compare current baseline/candidate inputs; never opens validation material."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from benchmarks.retrieval.adapters import split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
import omnichunk

p=argparse.ArgumentParser(); p.add_argument('--runtime',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert str(Path(omnichunk.__file__).resolve()).startswith(str(Path(a.runtime).resolve()))
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),
'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
result={'runtime_module':omnichunk.__file__,'cells':[]}
for model, path in models.items():
 counter=benchmark_counter('tokens',path,include_special_tokens=True)
 for domain in ('code','turkish'):
  corpus=load_corpus(Path('/workspace/work/omnichunk-v3')/domain/'development')
  assert all(d.split=='dev' for d in corpus.documents)
  for size in (64,96):
   for tool in ('omnichunk','omnichunk-pack') if 'baseline' not in a.runtime else ('omnichunk',):
    rows=[asdict(p) for d in corpus.documents for p in split_document(tool,d.source_id,d.path,d.text,size,counter,'tokens')]
    data=json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()
    result['cells'].append({'model':model,'domain':domain,'capacity':size,'tool':tool,'passage_count':len(rows),'passages':rows,'ordered_passage_sha256':hashlib.sha256(data).hexdigest(),'manifest_sha256':corpus.manifest_hash})
a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print([{'model':c['model'],'domain':c['domain'],'capacity':c['capacity'],'tool':c['tool'],'passages':c['passage_count'],'hash':c['ordered_passage_sha256']} for c in result['cells']])
