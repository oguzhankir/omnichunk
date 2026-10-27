"""Inclusive exploratory paired analysis and exact source-budget audit."""
import csv
from dataclasses import asdict
import gzip
import importlib.util
import json
from pathlib import Path
import random

spec=importlib.util.spec_from_file_location('parent_study',Path(__file__).with_name('study.py'))
s=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=s;spec.loader.exec_module(s)

H=Path(__file__).resolve().parent
d=json.loads(gzip.decompress((H/'results.json.gz').read_bytes()))
corpus=s.load_corpus(Path('/workspace/work/omnichunk-v3/code-files/development'))
counter=s.lru_cache(maxsize=100_000)(s.benchmark_counter('tokens',d['native_tokenizer'],include_special_tokens=True))
raw={doc.source_id:doc.text.encode('utf-8') for doc in corpus.documents}
gold={q.query_id:q.evidence for q in corpus.queries}
cluster_map=json.loads(Path('/workspace/work/omnichunk-v3/code-files/development/repository-clusters.json').read_text())
qcluster={q.query_id:cluster_map[q.evidence[0].source_id] for q in corpus.queries}
clusters=sorted(set(qcluster.values()));assert len(clusters)==15
indices={cluster:[q.query_id for q in corpus.queries if qcluster[q.query_id]==cluster] for cluster in clusters}
rng=random.Random(20261027)
draws=[rng.choices(clusters,k=len(clusters)) for _ in range(2000)]

def percentile(values,p):
    x=sorted(values);position=(len(x)-1)*p;i=int(position);fraction=position-i
    return x[i] if i==len(x)-1 else x[i]*(1-fraction)+x[i+1]*fraction

def paired(a,b):
    result={}
    ar={row['query_id']:row for row in a['rows']};br={row['query_id']:row for row in b['rows']}
    assert set(ar)==set(br)==set(gold)
    for metric in ['precision','recall','iou']:
        delta={qid:ar[qid]['metrics'][metric]-br[qid]['metrics'][metric] for qid in ar}
        sums={cluster:sum(delta[qid] for qid in ids) for cluster,ids in indices.items()}
        estimates=[sum(sums[c] for c in draw)/sum(len(indices[c]) for c in draw) for draw in draws]
        result[metric]={'mean_delta':sum(delta.values())/len(delta),
                        'wins':sum(v>1e-12 for v in delta.values()),'ties':sum(abs(v)<=1e-12 for v in delta.values()),'losses':sum(v < -1e-12 for v in delta.values()),
                        'bootstrap_delta_ci_95':[percentile(estimates,.025),percentile(estimates,.975)]}
    return result

refs={(o['tool'],o['capacity']):o for o in d['outputs'] if o['method']=='raw-prefix'}
by_key={(o['tool'],o['capacity'],o['method'],o['expansion_target']):o for o in d['outputs']}
comparisons=[];checks=0
assert d['protocol_sha256']==s.digest(H/'protocol.json');checks+=1
assert d['baseline_report_sha256']==s.digest(Path('/workspace/work/omnichunk-v3/dev/code-files/multilingual/baseline/report.json.gz'));checks+=1
assert d['model_calls']==d['rank_calls']==0;checks+=2
for output in d['outputs']:
    values={key:[] for key in ['precision','recall','iou']}
    for row in output['rows']:
        payloads=[]
        for span in row['spans']:
            text=raw[span['source_id']][span['start']:span['end']].decode('utf-8')
            assert text;payloads.append(text);checks+=1
        assert counter('\n\n'.join(payloads))<=512 if payloads else True;checks+=1
        calculated=asdict(s.score_evidence([s.EvidenceSpan(**span) for span in row['spans']],gold[row['query_id']]))
        assert calculated==row['metrics'];checks+=3
        for k in values:values[k].append(calculated[k])
        for i,span in enumerate(row['spans']):
            for other in row['spans'][i+1:]:
                if span['source_id']==other['source_id']:
                    assert min(span['end'],other['end'])<=max(span['start'],other['start']);checks+=1
    for key,series in values.items():
        assert abs(sum(series)/len(series)-output['summary'][key])<1e-12;checks+=1
    ref=refs[output['tool'],output['capacity']]
    entry={'tool':output['tool'],'capacity':output['capacity'],'method':output['method'],'expansion_target':output['expansion_target'],'versus_own_raw':paired(output,ref)}
    if output['method']=='public-hierarchy':
        entry['versus_same_anchor_source_window']=paired(output,by_key[output['tool'],output['capacity'],'source-window',output['expansion_target']])
    comparisons.append(entry)

analysis={'protocol_sha256':s.digest(H/'protocol.json'),'results_sha256':s.digest(H/'results.json.gz'),'groups':15,'queries':56,'bootstrap_replicates':2000,'seed':20261027,'bootstrap':'Repositoryclusters sampledwithreplacement,queryweightedmean inresampledgroups;unadjustedpercentile95CI. Descriptiveexploratoryallcomparisonsreported;no selected-positivecellleadershipclaim.','comparisons':comparisons}
(H/'paired.json').write_text(json.dumps(analysis,indent=2)+'\n')
with (H/'outcomes.csv').open('w',newline='') as f:
    writer=csv.writer(f);writer.writerow(['tool','capacity','workflow','expansion_target','queries','child_vectors','precision','recall','iou','mean_budget_used','recall_delta_vs_raw','recall_ci_lo','recall_ci_hi'])
    for output,comparison in zip(d['outputs'],comparisons):
        r=comparison['versus_own_raw']['recall']
        writer.writerow([output['tool'],output['capacity'],output['method'],output['expansion_target'],output['queries'],output['child_vectors'],*[output['summary'][k] for k in ['precision','recall','iou']],output['mean_budget_used'],r['mean_delta'],*r['bootstrap_delta_ci_95']])
audit={'checks':checks,'passed':checks,'protocol_sha256':s.digest(H/'protocol.json'),'results_sha256':s.digest(H/'results.json.gz'),'scope':'ExactcanonicalUTF8spans,complete512-tokenpayloads,nonoverlappingselectedranges,allmetricsandaggregatevalues. Allraw-prefixmetricsalsoassertedagainstoriginalbaselineinscoringscript.','files':{p.name:s.digest(p) for p in [H/'study.py',H/'protocol.json',H/'results.json.gz',H/'summary.json',H/'paired.json',H/'outcomes.csv',H/'native-cache-coverage.json',H/'native-protocol.json',H/'native_study.py']}}
(H/'artifact-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps({'checks':checks,'comparisons':len(comparisons),'groups':15}))
