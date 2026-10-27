"""All declared rows, exact-source audit, and inclusive exploratory comparisons."""
from dataclasses import asdict
import csv
import gzip
import importlib.util
import json
from pathlib import Path
import random
import statistics
import sys

H = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('final_parent_study', H/'study.py')
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)


def percentile(values, p):
    values = sorted(values)
    at = (len(values)-1)*p
    lo = int(at)
    return values[lo] if lo == len(values)-1 else values[lo]*(1-at+lo)+values[lo+1]*(at-lo)


def main():
    for name in ['combined-results.json.gz', 'paired.json', 'outcomes.csv', 'rival-comparisons.json']:
        if (H/name).exists():
            raise ValueError('Preserve completed analysis: '+name)
    final = json.loads(gzip.decompress((H/'results.json.gz').read_bytes()))
    baseline = json.loads(gzip.decompress((H.parent/'results.json.gz').read_bytes()))
    assert final['protocol_sha256'] == baseline['protocol_sha256'] == s.digest(H.parent/'protocol.json')
    assert final['protocol_addendum_sha256'] == s.digest(H/'protocol-addendum.json')
    assert final['model_calls'] == baseline['model_calls'] == final['rank_calls'] == baseline['rank_calls'] == 0
    corpus = s.load_corpus(Path('/workspace/work/omnichunk-v3/code-files/development'))
    assert final['corpus_manifest_sha256'] == baseline['corpus_manifest_sha256'] == corpus.manifest_hash
    assert final['native_tokenizer'] == baseline['native_tokenizer']
    assert final['candidate_report_sha256'] == s.digest(Path('/workspace/work/omnichunk-v3/dev/code-files/multilingual/candidate-final-c1/report.json.gz'))
    assert baseline['baseline_report_sha256'] == s.digest(Path('/workspace/work/omnichunk-v3/dev/code-files/multilingual/baseline/report.json.gz'))
    counter = s.lru_cache(maxsize=100_000)(s.benchmark_counter('tokens', final['native_tokenizer'], include_special_tokens=True))
    raw = {doc.source_id: doc.text.encode('utf-8') for doc in corpus.documents}
    gold = {q.query_id: q.evidence for q in corpus.queries}
    mapping = json.loads(Path('/workspace/work/omnichunk-v3/code-files/development/repository-clusters.json').read_text())
    clusters = sorted(set(mapping[q.evidence[0].source_id] for q in corpus.queries))
    ids = {cluster: [q.query_id for q in corpus.queries if mapping[q.evidence[0].source_id] == cluster] for cluster in clusters}
    assert len(clusters) == 15 and len(gold) == 56
    rng = random.Random(20261027)
    draws = [rng.choices(clusters, k=len(clusters)) for _ in range(2000)]

    def paired(a, b):
        aa = {row['query_id']: row for row in a['rows']}
        bb = {row['query_id']: row for row in b['rows']}
        assert set(aa) == set(bb) == set(gold)
        results = {}
        for metric in ['precision', 'recall', 'iou']:
            delta = {qid: aa[qid]['metrics'][metric]-bb[qid]['metrics'][metric] for qid in aa}
            sums = {cluster: sum(delta[qid] for qid in qids) for cluster, qids in ids.items()}
            estimates = [sum(sums[c] for c in draw)/sum(len(ids[c]) for c in draw) for draw in draws]
            results[metric] = {
                'mean_delta': statistics.mean(delta.values()),
                'wins': sum(x > 1e-12 for x in delta.values()),
                'ties': sum(abs(x) <= 1e-12 for x in delta.values()),
                'losses': sum(x < -1e-12 for x in delta.values()),
                'bootstrap_delta_ci_95': [percentile(estimates, .025), percentile(estimates, .975)],
            }
        return results

    outputs = []
    for version, source in [('baseline-e63', baseline), ('final-c1', final)]:
        for output in source['outputs']:
            outputs.append({'version': version, **output})
    assert len(baseline['outputs']) == 106 and len(final['outputs']) == 48 and len(outputs) == 154
    by_key = {(o['version'],o['tool'],o['capacity'],o['method'],o['expansion_target']): o for o in outputs}
    assert len(by_key) == len(outputs)
    refs = {(o['version'],o['tool'],o['capacity']): o for o in outputs if o['method'] == 'raw-prefix'}
    comparisons = []
    checks = 11
    for output in outputs:
        values = {key: [] for key in ['precision','recall','iou']}
        assert len(output['rows']) == output['queries'] == 56
        for row in output['rows']:
            payloads = []
            for span in row['spans']:
                text = raw[span['source_id']][span['start']:span['end']].decode('utf-8')
                assert text
                payloads.append(text)
                checks += 1
            used = counter('\n\n'.join(payloads)) if payloads else 0
            assert used <= 512 and used == row['budget_used']
            checks += 2
            calculated = asdict(s.score_evidence([s.EvidenceSpan(**span) for span in row['spans']],gold[row['query_id']]))
            assert calculated == row['metrics']
            checks += 3
            for key in values:
                values[key].append(calculated[key])
            for i, span in enumerate(row['spans']):
                for other in row['spans'][i+1:]:
                    if span['source_id'] == other['source_id']:
                        # Raw rank-prefix controls preserve their original ranges and
                        # can overlap; only expanded contexts promise a union.
                        if output['method'] not in ['raw-prefix', 'raw-top1']:
                            assert min(span['end'], other['end']) <= max(span['start'], other['start'])
                            checks += 1
        for key, series in values.items():
            assert abs(statistics.mean(series)-output['summary'][key]) < 1e-12
            checks += 1
        entry = {key: output[key] for key in ['version','tool','capacity','method','expansion_target']}
        entry['versus_own_raw'] = paired(output,refs[output['version'],output['tool'],output['capacity']])
        if output['method'] == 'public-hierarchy':
            entry['versus_same_anchor_source_window'] = paired(output,by_key[output['version'],output['tool'],output['capacity'],'source-window',output['expansion_target']])
        comparisons.append(entry)

    annotation = {
        'protocol_sha256': final['protocol_sha256'],
        'protocol_addendum_sha256': final['protocol_addendum_sha256'],
        'base_results_sha256': s.digest(H.parent/'results.json.gz'),
        'final_results_sha256': s.digest(H/'results.json.gz'),
        'model_calls': 0, 'rank_calls': 0,
        'scope': 'Secondary exploratory DEV workflow version extension; all old and final profile rows retained. No selection or primary claim change.',
        'bootstrap': '15 repository clusters sampled with replacement; query-weighted mean in resampled groups; 2000 replicates seed20261027. Unadjusted percentile95CI. All comparisons descriptive exploratory, no selected-positive-cell superiority claim.',
    }
    combined = {**annotation, 'corpus_manifest_sha256':corpus.manifest_hash, 'outputs':outputs}
    with (H/'combined-results.json.gz').open('wb') as f, gzip.GzipFile(fileobj=f,filename='',mtime=0,mode='wb') as z:
        z.write((json.dumps(combined,indent=2)+'\n').encode())
    (H/'combined-summary.json').write_text(json.dumps({**annotation,'outputs':[{k:v for k,v in o.items() if k!='rows'} for o in outputs]},indent=2)+'\n')
    (H/'paired.json').write_text(json.dumps({**annotation,'comparisons':comparisons},indent=2)+'\n')
    with (H/'outcomes.csv').open('w',newline='') as f:
        writer=csv.writer(f)
        writer.writerow(['version','tool','capacity','workflow','expansion_target','queries','child_vectors','precision','recall','iou','mean_budget_used','recall_delta_vs_own_raw','recall_ci_lo','recall_ci_hi'])
        for output, comparison in zip(outputs,comparisons):
            recall = comparison['versus_own_raw']['recall']
            writer.writerow([output['version'],output['tool'],output['capacity'],output['method'],output['expansion_target'],output['queries'],output['child_vectors'],*[output['summary'][k] for k in ['precision','recall','iou']],output['mean_budget_used'],recall['mean_delta'],*recall['bootstrap_delta_ci_95']])

    # Compare every final profile workflow to every named rival control at the
    # same child capacity. Raw/top1 use the matching raw control; expanded
    # methods use each rival's matching source-window target. No winner is chosen.
    rivals = [o for o in outputs if o['version']=='baseline-e63' and o['tool']!='omnichunk']
    rival_pairs = []
    for output in final['outputs']:
        for rival in rivals:
            if output['capacity'] != rival['capacity']:
                continue
            desired = 'source-window' if output['method']=='public-hierarchy' else output['method']
            if rival['method'] != desired or rival['expansion_target'] != output['expansion_target']:
                continue
            rival_pairs.append({
                'candidate': {k:output[k] for k in ['tool','capacity','method','expansion_target']},
                'rival': {k:rival[k] for k in ['version','tool','capacity','method','expansion_target']},
                'paired': paired(output,rival),
            })
    assert len(rival_pairs) == 432
    (H/'rival-comparisons.json').write_text(json.dumps({**annotation,'comparisons':rival_pairs},indent=2)+'\n')
    (H/'artifact-audit.json').write_text(json.dumps({**annotation,'checks':checks,'passed':checks,'workflow_rows':len(outputs),'own_raw_comparisons':len(comparisons),'matched_rival_comparisons':len(rival_pairs),'audit_scope':'Exact canonical UTF8 slices, complete counted512-token contexts including separators, exact metrics/aggregates, expanded range non-overlap, all raw-prefix metrics asserted vs source reports by scoring script.'},indent=2)+'\n')
    print(json.dumps({'checks':checks,'workflow_rows':len(outputs),'matched_rival_comparisons':len(rival_pairs)}),flush=True)


if __name__ == '__main__':
    main()
