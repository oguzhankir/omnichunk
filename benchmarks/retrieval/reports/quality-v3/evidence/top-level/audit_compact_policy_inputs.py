"""Check opt-in refactor against frozen third development variant; no embedding calls."""
from dataclasses import asdict
import gzip,json,hashlib
from pathlib import Path
from omnichunk import Chunker
from benchmarks.retrieval.adapters import _normalize
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
root=Path('/workspace/work/omnichunk-v3')
counter=benchmark_counter('tokens',Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),include_special_tokens=True)
checks=[]
for corpuspath,reportpath in [(root/'turkish/development',root/'dev/turkish/prose-fill-unconditional/report.json.gz'),(Path('/workspace/omnichunk/benchmarks/retrieval/corpus_v1'),Path('/workspace/work/omnichunk-quality/screen/v3-prose-fill-unconditional/corpus_v1/report.json')),(Path('/workspace/omnichunk/benchmarks/retrieval/corpus_squad_v1'),Path('/workspace/work/omnichunk-quality/screen/v3-prose-fill-unconditional/corpus_squad_v1/report.json'))]:
 if not reportpath.exists(): continue
 corpus=load_corpus(corpuspath)
 report=json.load(gzip.open(reportpath) if str(reportpath).endswith('.gz') else reportpath.open())
 for row in report['candidates']:
  cap=row['chunk_capacity'];rows=[]
  for doc in corpus.documents:
   if doc.split!='dev':continue
   chunks=Chunker(max_chunk_size=cap,min_chunk_size=0,size_unit='tokens',tokenizer=counter,context_mode='none',coverage_policy='lossless',overlap=None,overlap_lines=0,nws_backend='python',prose_boundary_policy='compact').chunk(doc.path,doc.text)
   rows.extend(asdict(p) for p in _normalize(doc.source_id,doc.text,[c.text for c in chunks],cap,counter))
  assert rows==row['passages'],(corpuspath,cap)
  checks.append({'corpus':corpus.corpus_id,'capacity':cap,'passages':len(rows),'exact_ordered_passages':True,'report_sha256':hashlib.sha256(reportpath.read_bytes()).hexdigest()})
assert len(checks)==6, len(checks)
(root/'compact-policy-input-equivalence.json').write_text(json.dumps({'from_variant':'fca2240','no_inference':True,'checks':checks,'all_passed':True},indent=2)+'\n')
print(checks)
