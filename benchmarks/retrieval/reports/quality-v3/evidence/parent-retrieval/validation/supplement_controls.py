"""Retain the separate frozen Chonkie96 controls and explicit Chonkie64 failure."""
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import importlib.util
import json
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('validation_base_workflow',HERE/'baseline/study.py')
s=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=s
spec.loader.exec_module(s)


def main():
    output=HERE/'supplement-results.json.gz'
    if output.exists():raise ValueError('Preserve completed controls')
    root=Path('/workspace/work/omnichunk-v3/validation/code-files/multilingual')
    report_path=root/'baseline-valid-96/report.json.gz'
    failure_path=root/'failures/chonkie-sentence-64/report.json'
    report=json.loads(gzip.decompress(report_path.read_bytes()))
    failure=json.loads(failure_path.read_text())
    corpus=s.load_corpus(Path('/workspace/work/omnichunk-v3/code-files/validation'))
    assert corpus.manifest_hash==report['corpus_manifest_sha256']==failure['corpus_manifest_sha256']
    count=s.lru_cache(maxsize=100_000)(s.benchmark_counter('tokens',report['configuration']['tokenizer'],include_special_tokens=True))
    tokenizer=s.AutoTokenizer.from_pretrained(report['configuration']['tokenizer'],local_files_only=True,trust_remote_code=False)
    docs={doc.source_id:s.Document(doc.source_id,doc.text,tokenizer,count) for doc in corpus.documents}
    outputs=[]
    assert len(report['candidates'])==len(failure['candidates'])==1
    c=report['candidates'][0]
    assert c['tool']=='chonkie-sentence' and c['chunk_capacity']==96 and c['status']=='ok'
    for method,target in [('raw-prefix',512),('raw-top1',96),*[('source-window',n) for n in [128,256,512]]]:
        rows=[]
        for q in c['per_query']:
            anchors=[s.Span(p['source_id'],p['start'],p['end']) for p in q['ranks']]
            if method=='raw-prefix':
                by_id={p['passage_id']:p for p in c['passages']}
                selected=[s.Span(by_id[k]['source_id'],by_id[k]['start'],by_id[k]['end']) for k in q['budget_passage_ids']]
                used=q['budget_used']
            elif method=='raw-top1':
                selected=anchors[:1]
                used=count(docs[selected[0].source_id].payload(selected[0])) if selected else 0
            else:
                selected,used=s.assemble([docs[a.source_id].window(a.start,a.end,target) for a in anchors],docs,count)
            metrics=asdict(s.score_evidence([s.EvidenceSpan(x.source_id,x.start,x.end) for x in selected],[s.EvidenceSpan(**e) for e in q['evidence']]))
            if method=='raw-prefix':assert metrics==q['evidence_at_budget']
            rows.append({'query_id':q['query_id'],'metrics':metrics,'budget_used':used,'spans':[asdict(x) for x in selected],'mapping':{'native_leaf':0,'containing_parent':0,'source_window_fallback':0},'top1_source_hit':bool(anchors and anchors[0].source_id in {e['source_id'] for e in q['evidence']})})
        outputs.append({'tool':c['tool'],'capacity':96,'method':method,'expansion_target':target,'status':'ok','summary':{k:statistics.mean(r['metrics'][k] for r in rows) for k in ['precision','recall','iou']},'queries':len(rows),'child_vectors':c['chunks'],'mean_budget_used':statistics.mean(r['budget_used'] for r in rows),'mapping_counts':{'native_leaf':0,'containing_parent':0,'source_window_fallback':0},'rows':rows,'input_report_sha256':s.digest(report_path)})
    f=failure['candidates'][0]
    assert f['tool']=='chonkie-sentence' and f['chunk_capacity']==64 and f['status']=='error'
    for method,target in [('raw-prefix',512),('raw-top1',64),*[('source-window',n) for n in [128,256,512]]]:
        outputs.append({'tool':f['tool'],'capacity':64,'method':method,'expansion_target':target,'status':'error','detail':f['detail'],'summary':None,'queries':0,'expected_queries':56,'child_vectors':None,'mean_budget_used':None,'mapping_counts':{'native_leaf':0,'containing_parent':0,'source_window_fallback':0},'rows':[],'failure_report_sha256':s.digest(failure_path),'failure_report':str(failure_path),'failure_scope':'Frozen adapter source/canonical-budget conformance failure before dense evaluation; no workflow score, repair, per-file filtering or rerun.'})
    result={'scope':'Complete fixed-grid control inventory: separate successful96 report and explicit64 failure. No parameter or score-based selection.','created_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':s.digest(HERE.parent/'protocol.json'),'protocol_addendum_sha256':s.digest(HERE/'protocol-addendum.json'),'script_sha256':s.digest(Path(__file__)),'corpus_manifest_sha256':corpus.manifest_hash,'native_tokenizer':report['configuration']['tokenizer'],'input_report_sha256':s.digest(report_path),'failure_report_sha256':s.digest(failure_path),'model_calls':0,'rank_calls':0,'outputs':outputs}
    with output.open('xb') as raw,gzip.GzipFile(fileobj=raw,filename='',mtime=0,mode='wb') as z:z.write((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps({'success_rows':5,'explicit_failure_rows':5,'output_sha256':s.digest(output)}),flush=True)


if __name__=='__main__':main()
