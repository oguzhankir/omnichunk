"""Exploratory code-context conformance only: no ranking, labels or embeddings."""
from __future__ import annotations
import hashlib,json,sys
from dataclasses import asdict
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,'/workspace/omnichunk')
from omnichunk import Chunker
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
root=Path('/workspace/work/omnichunk-v3')
manifest=root/'code/development/manifest.json'
metadata=json.loads(manifest.read_text()); byid={d['source_id']:d for d in metadata['documents']}
corpus=load_corpus(manifest)
models={'multilingual':Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'english':Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip()}
protocol={'scope':'exploratory conformance/index-work only; no retrieval scores or inference','recorded_utc':datetime.now(timezone.utc).isoformat(),'manifest_sha256':corpus.manifest_hash,'modes':['none','minimal','full'],'path_policies':['artifact','original-source-path'],'capacities':[64,96],'counter':'native full input with special tokens; truncation False','source_validation':'chunk.text must equal canonical UTF8 slice; lossless disjoint ranges cover full source','rendered_policy':'chunk.contextualized_text is encoder input, raw source ranges remain evidence coordinates; derived context is not additional evidence','context_overflow':'omit (native default)','overlap':0,'preprocessing':'no rewrite or label-derived enrichment'}
(root/'adapter-audit/context-protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
out={}
for model,snapshot in models.items():
 counter=benchmark_counter('tokens',snapshot,include_special_tokens=True)
 for policy in protocol['path_policies']:
  for mode in protocol['modes']:
   for capacity in protocol['capacities']:
    rows=[]
    for doc in corpus.documents:
     if doc.split!='dev':continue
     path=doc.path if policy=='artifact' else byid[doc.source_id]['function']['path']
     chunks=Chunker(max_chunk_size=capacity,min_chunk_size=0,size_unit='tokens',tokenizer=counter,context_mode=mode,context_overflow='omit',coverage_policy='lossless',overlap=None,overlap_lines=0,nws_backend='python').chunk(path,doc.text)
     raw=doc.text.encode('utf-8');cursor=0
     for chunk in chunks:
      assert chunk.byte_range.start==cursor
      assert raw[chunk.byte_range.start:chunk.byte_range.end].decode('utf-8')==chunk.text
      assert counter(chunk.contextualized_text)<=capacity
      cursor=chunk.byte_range.end
     assert cursor==len(raw)
     rows.append({'source_id':doc.source_id,'path':path,'passages':len(chunks),'raw_tokens':sum(counter(c.text) for c in chunks),'rendered_tokens':sum(counter(c.contextualized_text) for c in chunks),'rendered_changed':sum(c.text!=c.contextualized_text for c in chunks),'context_omitted':sum(bool(c.metadata.get('context_omitted')) for c in chunks),'records':[{'start':c.byte_range.start,'end':c.byte_range.end,'raw_text_sha256':hashlib.sha256(c.text.encode()).hexdigest(),'rendered_text_sha256':hashlib.sha256(c.contextualized_text.encode()).hexdigest(),'rendered_tokens':counter(c.contextualized_text),'rendered_text':c.contextualized_text} for c in chunks]})
    key=f'{model}-{policy}-{mode}-{capacity}'
    totals={f:sum(r[f] for r in rows) for f in ['passages','raw_tokens','rendered_tokens','rendered_changed','context_omitted']}
    out[key]={'documents':len(rows),'totals':totals,'rows':rows}
    print(key,totals,flush=True)
(root/'adapter-audit/context-conformance.json').write_text(json.dumps(out,indent=2)+'\n')
