"""Declared exploratory DEV-only derived-context comparison; no runtime API changes."""
from __future__ import annotations
import gzip,hashlib,importlib.metadata,json,os,platform,subprocess,sys,time
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,'/workspace/omnichunk')
from omnichunk import Chunker
from omnichunk.retrieval_eval import EvidenceSpan,score_evidence,score_ranking
from benchmarks.prepare_dense import _configure_cpu_threads,_load_model,model_files
from benchmarks.retrieval.adapters import Passage,split_document
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.dense import build_dense_artifact,FrozenDenseRetriever
from benchmarks.retrieval.ranking import select_budget
from benchmarks.retrieval.tokenization import benchmark_counter
from benchmarks.compare_retrieval import compare_reports
ROOT=Path('/workspace/work/omnichunk-v3')
OUT=ROOT/'context-dense-development'
OUT.mkdir(exist_ok=False)
corpus_path=ROOT/'code/development/manifest.json'
corpus=load_corpus(corpus_path)
manifest=json.loads(corpus_path.read_text()); bysource={d['source_id']:d for d in manifest['documents']}
cluster_map=json.loads((corpus_path.parent/'repository-clusters.json').read_text())
models=[('multilingual','sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','e8f8c211226b894fcb81acc59f3b34ba3efd5f42',Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip()),('english','sentence-transformers/all-MiniLM-L6-v2','1110a243fdf4706b3f48f1d95db1a4f5529b4d41',Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip())]
profiles=['omni-raw','omni-minimal-original-path','fixed-raw','fixed-original-path-prefix']
protocol={'schema_version':1,'recorded_utc':datetime.now(timezone.utc).isoformat(),'scope':'Exploratory development only; no heldout access; not historical exact-source adapter contract','corpus_manifest_sha256':corpus.manifest_hash,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'profiles':profiles,'path_policy':'original function.path from attribution manifest for all four profiles; raw variants do not render it','fixed_prefix':'# {last three POSIX filepath components} followed by two newlines, added only when complete prefix+raw fits; otherwise raw payload','omni_context':'existing context_mode=minimal,context_overflow=omit; includes filepath,language and available imports; no generated or query-derived enrichment','source_evidence':'validate raw chunk.text exact UTF8 slice before constructing modelpayload Passage; derived text contributes NO extra gold bytes','capacities':[64,96],'primary_retrieval_budget':512,'sensitivity_retrieval_budgets':[128,256],'top_k':5,'overlap':0,'coverage_policy':'lossless','counter':'native HF add_special_tokens=True,truncation=False','model_contract':'standard local pretrained Transformer+meanPooling(+Normalize), CPU2threads,batch32,no prompts','selection':'Record all four profiles/both models/capacities/budgets; no selection using validation; no independent latency claim','models':[{'id':x[1],'revision':x[2]} for x in models]}
(OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
_configure_cpu_threads(2)

def dump(path,value):
 raw=(json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode()
 path.write_bytes(gzip.compress(raw,mtime=0) if path.suffix=='.gz' else raw)

def passage(source,start,end,payload):
 digest=hashlib.sha256(f'{source}\0{start}\0{end}\0{payload}'.encode()).hexdigest()
 return Passage(digest,source,start,end,payload)

all_summaries={}
for label,model_id,revision,snapshot in models:
 directory=Path(snapshot); counter=benchmark_counter('tokens',snapshot,include_special_tokens=True)
 files=model_files(directory)
 selected={}; provenance={}
 for profile in profiles:
  for capacity in [64,96]:
   passages=[]; records=[]
   for doc in corpus.documents:
    if doc.split!='dev':continue
    raw=doc.text.encode(); path=bysource[doc.source_id]['function']['path']
    if profile.startswith('omni'):
     mode='none' if profile=='omni-raw' else 'minimal'
     chunks=Chunker(max_chunk_size=capacity,min_chunk_size=0,size_unit='tokens',tokenizer=counter,context_mode=mode,context_overflow='omit',coverage_policy='lossless',overlap=None,overlap_lines=0,nws_backend='python').chunk(path,doc.text)
     units=[(c.byte_range.start,c.byte_range.end,c.text,c.contextualized_text,bool(c.metadata.get('context_omitted'))) for c in chunks]
    else:
     fixed=split_document('fixed',doc.source_id,path,doc.text,capacity,counter,'tokens')
     units=[]
     for p in fixed:
      prefix='# '+'/'.join(path.replace('\\','/').split('/')[-3:])+'\n\n'
      enriched=prefix+p.text
      use_prefix=profile=='fixed-original-path-prefix' and counter(enriched)<=capacity
      units.append((p.start,p.end,p.text,enriched if use_prefix else p.text,profile=='fixed-original-path-prefix' and not use_prefix))
    cursor=0
    for start,end,text,payload,omitted in units:
     assert start==cursor and raw[start:end].decode('utf-8')==text
     assert counter(payload)<=capacity
     cursor=end
     p=passage(doc.source_id,start,end,payload);passages.append(p)
     records.append({'passage_id':p.passage_id,'source_id':p.source_id,'start':start,'end':end,'raw_sha256':hashlib.sha256(text.encode()).hexdigest(),'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),'raw_tokens':counter(text),'payload_tokens':counter(payload),'derived':payload!=text,'context_omitted':omitted})
    assert cursor==len(raw)
   selected[(profile,capacity)]=passages
   provenance[(profile,capacity)]=records
 dump(OUT/f'{label}-payload-source-audit.json.gz',[{'profile':p,'capacity':c,'records':provenance[(p,c)],'passages':[asdict(x) for x in selected[(p,c)]]} for p,c in selected])
 model=_load_model(directory);limit=model.max_seq_length
 packages={n:importlib.metadata.version(n) for n in ['torch','transformers','sentence-transformers','tokenizers','numpy']}
 stats={'unique_texts':0,'native_input_tokens':0,'batches':0,'maximum_input_tokens':0,'encoding_seconds':0.0}
 def embed(role,texts):
  tokenized=model.tokenizer(list(texts),truncation=False,add_special_tokens=True,padding=False)
  ids=tokenized['input_ids'];lengths=[len(x) for x in ids]
  if max(lengths,default=0)>limit:raise ValueError('Native model input would truncate')
  native=model.tokenize(list(texts));unmasked=[[int(t) for t,m in zip(row,mask) if int(m)] for row,mask in zip(native['input_ids'].tolist(),native['attention_mask'].tolist())]
  assert unmasked==ids
  stats['unique_texts']+=len(texts);stats['native_input_tokens']+=sum(lengths);stats['batches']+=1;stats['maximum_input_tokens']=max(stats['maximum_input_tokens'],max(lengths,default=0))
  t=time.perf_counter();vectors=model.encode(list(texts),batch_size=32,prompt='',normalize_embeddings=False,convert_to_numpy=True,show_progress_bar=False)
  stats['encoding_seconds']+=time.perf_counter()-t
  return vectors.tolist()
 vectors_path=OUT/f'{label}-vectors.json'
 producer={'model_files':files,'packages':packages,'prompt':'','max_sequence_length':limit,'supported_pipeline':'standard Transformer + mean Pooling (+ Normalize)','device':'cpu','input_policy':'native complete inputs, specials included, reject overflow','normalization':'cosine normalized on artifact load','protocol_sha256':hashlib.sha256((OUT/'protocol.json').read_bytes()).hexdigest(),'script_sha256':protocol['script_sha256'],'torch_threads':2,'torch_interop_threads':2}
 t=time.perf_counter()
 artifact=build_dense_artifact(vectors_path,corpus_manifest_sha256=corpus.manifest_hash,model_id=model_id,model_revision=revision,preprocessing_revision='explicit-original-source-context-v1',passages=[p.text for ps in selected.values() for p in ps],queries=[q.text for q in corpus.queries if q.split=='dev'],embed=embed,batch_size=32,producer_metadata=producer)
 assert model_files(directory)==files
 retriever=FrozenDenseRetriever(vectors_path,corpus_manifest_sha256=corpus.manifest_hash)
 preparation={'seconds_including_encoding':time.perf_counter()-t,'workload':stats,'artifact':artifact,'producer':producer,'python':sys.version,'platform':platform.platform(),'runtime_git_revision':subprocess.run(['git','rev-parse','HEAD'],cwd='/workspace/omnichunk',capture_output=True,text=True,check=True).stdout.strip(),'runtime_source_files':{str(p.relative_to('/workspace/omnichunk')):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/workspace/omnichunk/src/omnichunk').rglob('*.py')}}
 dump(OUT/f'{label}-preparation.json',preparation)
 reports={budget:[] for budget in [128,256,512]}
 for (profile,capacity),passages in selected.items():
  index=retriever.index(passages);rows={b:[] for b in reports}
  for query in corpus.queries:
   if query.split!='dev':continue
   ranked=index.rank(query.text)
   qrels={p.passage_id:1.0 for p in passages if any(p.source_id==e.source_id and max(p.start,e.start)<min(p.end,e.end) for e in query.evidence)}
   ranking=asdict(score_ranking([p.passage_id for p,_ in ranked],qrels,k=5))
   for budget in reports:
    retrieved=select_budget(ranked,budget,counter)
    spans=[EvidenceSpan(p.source_id,p.start,p.end) for p,_ in retrieved]
    rows[budget].append({'query_id':query.query_id,'query':query.text,'language':'en','category':'code','evidence':[asdict(x) for x in query.evidence],'ranking':ranking,'budget_used':counter('\n\n'.join(p.text for p,_ in retrieved)) if retrieved else 0,'evidence_at_budget':asdict(score_evidence(spans,query.evidence)),'budget_passage_ids':[p.passage_id for p,_ in retrieved]})
  for budget in reports:
   records=provenance[(profile,capacity)];summary={m:sum(r['evidence_at_budget'][m] for r in rows[budget])/len(rows[budget]) for m in ['precision','recall','iou']}
   candidate={'tool':profile,'chunk_capacity':capacity,'status':'ok','passage_count':len(passages),'payload_tokens':sum(r['payload_tokens'] for r in records),'raw_tokens':sum(r['raw_tokens'] for r in records),'derived_passages':sum(r['derived'] for r in records),'context_omitted':sum(r['context_omitted'] for r in records),'summary':summary,'per_query':rows[budget]}
   reports[budget].append(candidate)
   print(label,budget,profile,capacity,summary,'vectors',len(passages),'tokens',candidate['payload_tokens'],flush=True)
 for budget,candidates in reports.items():
  report={'schema_version':2,'corpus_manifest_sha256':corpus.manifest_hash,'queries':sum(q.split=='dev' for q in corpus.queries),'documents':len(corpus.documents),'configuration':{'split':'dev','unit':'tokens','tokenizer':snapshot,'include_special_tokens':True,'retrieval_budget':budget,'top_k':5,'context':'EXPLORATORY per-profile derived encoder text; exact raw evidence ranges','overlap':0,'retriever':'frozen-dense-cosine-v1','idf_fit':None,'relevance':'source span intersection','budget_selection':'whole ranked prefix, including two newline separators','chunk_sizes':[64,96],'dense_embeddings':retriever.metadata},'protocol':protocol,'candidates':candidates}
  dump(OUT/f'{label}-budget-{budget}.json.gz',report)
  for reference in profiles:
   if reference=='omni-minimal-original-path':continue
   paired=compare_reports(report,report,baseline_tool=reference,candidate_tool='omni-minimal-original-path',cluster_map=cluster_map)
   dump(OUT/f'{label}-{budget}-minimal-vs-{reference}.json',paired)
  all_summaries[f'{label}-{budget}']=[{k:v for k,v in c.items() if k!='per_query'} for c in candidates]
 dump(vectors_path.with_suffix('.json.gz'),json.loads(vectors_path.read_text()));vectors_path.unlink()
 del model,retriever
 dump(OUT/'summary.json',all_summaries)
print('COMPLETED',OUT,flush=True)
