"""Public hierarchy native leaves, using exact cached embeddings or no result."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys

spec=importlib.util.spec_from_file_location('parent_study',Path(__file__).with_name('study.py'))
s=importlib.util.module_from_spec(spec);sys.modules[spec.name]=s;spec.loader.exec_module(s)
from benchmarks.retrieval.adapters import Passage, _passage
from benchmarks.retrieval.dense import FrozenDenseRetriever, text_sha256


def stream_records(path):
    """Decode only one bounded record at a time; validate the complete raw SHA."""
    digest=hashlib.sha256();decoder=json.JSONDecoder();buffer='';started=False
    with gzip.open(path,'rb') as f:
        def read():
            chunk=f.read(65536);digest.update(chunk);return chunk.decode('utf-8')
        while True:
            if not started:
                buffer+=read()
                marker='  "records": ['
                i=buffer.find(marker)
                if i<0:
                    if len(buffer)>2_000_000:raise ValueError('Unexpected vector header')
                    continue
                buffer=buffer[i+len(marker):];started=True
            buffer=buffer.lstrip(' \r\n\t,')
            if buffer.startswith(']'):
                while True:
                    chunk=read()
                    if not chunk:break
                return digest.hexdigest()
            try:
                obj,end=decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk=read()
                if not chunk:raise ValueError('Truncated record')
                buffer+=chunk;continue
            buffer=buffer[end:]
            yield obj


def main():
    H=s.HERE
    report_path=Path('/workspace/work/omnichunk-v3/dev/code-files/multilingual/baseline/report.json.gz')
    baseline=json.loads(gzip.decompress(report_path.read_bytes()))
    corpus=s.load_corpus(Path('/workspace/work/omnichunk-v3/code-files/development'))
    snapshot=baseline['configuration']['tokenizer']
    count=s.lru_cache(maxsize=100_000)(s.benchmark_counter('tokens',snapshot,include_special_tokens=True))
    tokenizer=s.AutoTokenizer.from_pretrained(snapshot,local_files_only=True,trust_remote_code=False)
    docs={doc.source_id:s.Document(doc.source_id,doc.text,tokenizer,count) for doc in corpus.documents}
    trees={};wanted={('query',text_sha256(q.text)) for q in corpus.queries};query_by_id={q.query_id:q for q in corpus.queries}
    for capacity in [64,96]:
        by_source={}
        for doc in corpus.documents:
            tree=s.Chunker(size_unit='tokens',tokenizer=count,context_mode='none').hierarchical_chunk(doc.path,doc.text,source_id=doc.source_id,levels=[capacity,128,256,512])
            by_source[doc.source_id]=tree
            for leaf in tree.leaves():
                wanted.add(('passage',text_sha256(leaf.text)))
                assert docs[doc.source_id].raw[leaf.byte_range.start:leaf.byte_range.end].decode()==leaf.text
                assert count(leaf.text)<=capacity
        trees[capacity]=by_source
    prior=Path('/workspace/work/omnichunk-v3/dev/code-files/multilingual/baseline/vectors.json.gz')
    kept={};iterator=stream_records(prior)
    while True:
        try:record=next(iterator)
        except StopIteration as stop:
            raw_sha=stop.value;break
        key=(record['role'],record['text_sha256'])
        if key in wanted:
            if key in kept:raise ValueError('Duplicate cache key')
            kept[key]=record
    assert raw_sha==baseline['configuration']['dense_embeddings']['artifact_sha256']
    missing=wanted-set(kept)
    coverage={'protocol_sha256':s.digest(H/'native-protocol.json'),'baseline_raw_artifact_sha256':raw_sha,'wanted_records':len(wanted),'available_records':len(kept),'missing_records':len(missing),'missing_keys':[list(k) for k in sorted(missing)],'model_calls':0}
    (H/'native-cache-coverage.json').write_text(json.dumps(coverage,indent=2)+'\n')
    if missing:
        print(json.dumps(coverage)[:1000]);return
    old=baseline['configuration']['dense_embeddings']
    data={key:old[key] for key in ['schema_version','corpus_manifest_sha256','model_id','model_revision','preprocessing_revision','dimension','overflow_policy']}
    data['records']=[kept[key] for key in sorted(kept)]
    data['producer_metadata']={'model_files':old['producer_metadata']['model_files'],'prior_artifact_sha256':raw_sha,'script_sha256':s.digest(Path(__file__)),'actual_encoder_calls':0,'scope':'Exact role/text-digest raw-vector subset from verified real pretrained baseline; no new inference. Original preparation costs belong to baseline.'}
    artifact=H/'native-subset-vectors.json'
    if artifact.exists():raise ValueError('Preserve existing output')
    artifact.write_text(json.dumps(data,indent=2)+'\n')
    retriever=FrozenDenseRetriever(artifact,corpus_manifest_sha256=corpus.manifest_hash)
    outputs=[]
    for capacity,by_source in trees.items():
        passages=[];parent_map={}
        for source_id,tree in by_source.items():
            for leaf in tree.leaves():
                p=_passage(source_id,leaf.byte_range.start,leaf.byte_range.end,leaf.text);passages.append(p)
                parents={};current=leaf
                for target in [128,256,512]:
                    current=tree.parent(current);assert current is not None
                    span=s.Span(source_id,current.byte_range.start,current.byte_range.end)
                    assert docs[source_id].payload(span)==current.text and count(current.text)<=target
                    parents[target]=span
                parent_map[p.passage_id]=parents
        index=retriever.index(passages)
        ranked={q.query_id:index.rank(q.text) for q in corpus.queries}
        for method,target in [('raw-prefix',512),*[('source-window',v) for v in [128,256,512]],*[('public-hierarchy-native',v) for v in [128,256,512]]]:
            rows=[]
            for q in corpus.queries:
                ranks=ranked[q.query_id]
                if method=='raw-prefix':
                    selected=s.assemble([s.Span(p.source_id,p.start,p.end) for p,_ in ranks],docs,count)[0]
                else:
                    windows=[]
                    for p,_ in ranks[:5]:
                        if method=='source-window':window=docs[p.source_id].window(p.start,p.end,target)
                        else:window=parent_map[p.passage_id][target]
                        windows.append(window)
                    selected=s.assemble(windows,docs,count)[0]
                metrics=s.asdict(s.score_evidence([s.EvidenceSpan(x.source_id,x.start,x.end) for x in selected],q.evidence))
                rows.append({'query_id':q.query_id,'metrics':metrics,'spans':[s.asdict(x) for x in selected]})
            summary={key:statistics.mean(x['metrics'][key] for x in rows) for key in ['precision','recall','iou']}
            outputs.append({'tool':'native-hierarchy-leaves','capacity':capacity,'method':method,'expansion_target':target,'summary':summary,'queries':len(rows),'child_vectors':len(passages),'rows':rows})
            print(capacity,method,target,summary,flush=True)
    result={'schema_version':1,'protocol_sha256':s.digest(H/'native-protocol.json'),'script_sha256':s.digest(Path(__file__)),'baseline_artifact_sha256':raw_sha,'model_calls':0,'rank_calls':len(corpus.queries)*2,'corpus_manifest_sha256':corpus.manifest_hash,'outputs':outputs,'limitations':['Exploratory development-only workflow','Native hierarchy min-size leaves differ from raw benchmarkOmni; compare expansions to their ownraw childbaseline','Allsame-sized source-window competitorcontrols fromfirststudy retained']}
    out=H/'native-results.json.gz'
    with out.open('wb') as f,gzip.GzipFile(fileobj=f,filename='',mtime=0,mode='wb') as z:z.write((json.dumps(result,indent=2)+'\n').encode())
    (H/'native-summary.json').write_text(json.dumps({**{k:v for k,v in result.items() if k!='outputs'},'outputs':[{k:v for k,v in x.items() if k!='rows'} for x in outputs]},indent=2)+'\n')


if __name__=='__main__':main()
