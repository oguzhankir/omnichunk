import json,sys
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,'/workspace/omnichunk')
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
from omnichunk import Chunker
counter=benchmark_counter('tokens', Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),include_special_tokens=True)
rows=[]
for corpus_name in ['corpus_v1','corpus_squad_v1']:
 corpus=load_corpus(Path('/workspace/omnichunk/benchmarks/retrieval')/corpus_name)
 for capacity in [64,96]:
  options={} if sys.argv[1]!='pack' else {'markdown_paragraph_policy':'pack'}
  chunker=Chunker(max_chunk_size=capacity,min_chunk_size=0,size_unit='tokens',tokenizer=counter,context_mode='none',coverage_policy='lossless',**options)
  counts=defaultdict(lambda:{'documents':0,'chunks':0,'native_tokens':0,'bytes':0})
  for doc in corpus.documents:
   if doc.split!='dev':continue
   chunks=chunker.chunk(doc.path,doc.text)
   assert ''.join(c.text for c in chunks)==doc.text
   raw=doc.text.encode()
   for c in chunks:
    assert raw[c.byte_range.start:c.byte_range.end].decode()==c.text
    assert counter(c.contextualized_text)<=capacity
   key=doc.category
   counts[key]['documents']+=1;counts[key]['chunks']+=len(chunks);counts[key]['native_tokens']+=sum(counter(c.text) for c in chunks);counts[key]['bytes']+=len(raw)
  rows.append({'corpus':corpus_name,'capacity':capacity,'categories':dict(counts)})
print(json.dumps({'label':sys.argv[1],'coverage':'lossless','rows':rows},indent=2))
