import json,sys
from pathlib import Path
from statistics import mean
sys.path.insert(0,'/workspace/omnichunk')
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
from benchmarks.retrieval.ranking import LexicalRetriever,select_budget
from benchmarks.retrieval.adapters import _normalize
from omnichunk import Chunker, EvidenceSpan, score_evidence
counter=benchmark_counter('tokens',Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),include_special_tokens=True)
rows=[]
for name in ['corpus_v1','corpus_squad_v1']:
 corpus=load_corpus(Path('/workspace/omnichunk/benchmarks/retrieval')/name)
 docs=[d for d in corpus.documents if d.split=='dev']; queries=[q for q in corpus.queries if q.split=='dev']
 retriever=LexicalRetriever([d.text for d in docs])
 for capacity in [64,96]:
  options={} if sys.argv[1]!='pack' else {'markdown_paragraph_policy':'pack'}
  chunker=Chunker(max_chunk_size=capacity,min_chunk_size=0,size_unit='tokens',tokenizer=counter,context_mode='none',coverage_policy='lossless',nws_backend='python',**options)
  passages=[]
  for doc in docs:
   chunks=chunker.chunk(doc.path,doc.text)
   assert ''.join(c.text for c in chunks)==doc.text
   passages.extend(_normalize(doc.source_id,doc.text,[c.text for c in chunks],capacity,counter))
  index=retriever.index(passages)
  out=[]
  for query in queries:
   ranked=index.rank(query.text)
   selected=select_budget(ranked,512,counter)
   metrics=score_evidence([EvidenceSpan(p.source_id,p.start,p.end) for p,_ in selected],query.evidence)
   out.append({'id':query.query_id,'recall':metrics.recall,'precision':metrics.precision,'iou':metrics.iou})
  rows.append({'corpus':name,'capacity':capacity,'chunks':len(passages),'native_tokens':sum(counter(p.text) for p in passages),'recall':mean(q['recall'] for q in out),'precision':mean(q['precision'] for q in out),'iou':mean(q['iou'] for q in out),'per_query':out})
print(json.dumps({'label':sys.argv[1],'model':'lexical-char-2-4-tfidf-v1','retrieval_budget':512,'development_only':True,'rows':rows},indent=2))
