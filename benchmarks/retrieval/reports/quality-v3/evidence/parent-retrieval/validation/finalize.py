"""Verify row commitments, label native/mapped workflows, and bind artifacts."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def main():
    if (HERE/'manifest.json').exists():
        raise ValueError('Preserve completed manifest')
    result_path = HERE/'combined-results.json.gz'
    result = json.loads(gzip.decompress(result_path.read_bytes()))
    commitments = json.loads(gzip.decompress((HERE/'row-hashes.json.gz').read_bytes()))
    independent = json.loads((HERE/'identity-cache-audit.json').read_text())
    audit = json.loads((HERE/'artifact-audit.json').read_text())
    assert independent['integrity_passed']
    assert result['model_calls'] == result['rank_calls'] == independent['model_calls'] == independent['rank_calls'] == 0
    assert commitments['combined_results_sha256'] == file_sha(result_path)
    assert independent['corpus_manifest_sha256'] == result['corpus_manifest_sha256']
    for key in ['baseline','candidate-final-d0']:
        assert independent['artifacts'][key]['report_compressed_sha256'] == file_sha(Path('/workspace/work/omnichunk-v3/validation/code-files/multilingual')/key/'report.json.gz')
    assert len(result['outputs']) == len(commitments['rows']) == 154
    row_checks = 0
    statuses = []
    identities = {(r['tool'],r['capacity']):r for r in independent['identity']}
    for workflow, commitment in zip(result['outputs'],commitments['rows']):
        assert value_sha(workflow) == commitment['workflow_row_sha256']
        row_checks += 1
        for row, hashed in zip(workflow['rows'],commitment['query_rows']):
            assert row['query_id'] == hashed['query_id'] and value_sha(row) == hashed['sha256']
            row_checks += 1
        if workflow['method'] == 'public-hierarchy':
            candidate_identity = identities.get((workflow['tool'],workflow['capacity'])) if workflow['version']=='final-d0' else None
            exact = bool(candidate_identity and candidate_identity['full_source_range_text_passage_id_set_identical'] and independent['all_wanted_in_candidate_alone'] and workflow['mapping_counts']=={'native_leaf':280,'containing_parent':0,'source_window_fallback':0})
            statuses.append({
                **{key:workflow[key] for key in ['version','tool','capacity','method','expansion_target']},
                'label':'native-leaf-indexed-exact-ancestry' if exact else 'source-span-mapped-with-declared-fallback',
                'full_index_identity_independently_verified':bool(candidate_identity and candidate_identity['full_source_range_text_passage_id_set_identical']),
                'native_cache_complete':independent['all_wanted_in_candidate_alone'],
                'mapping_counts':workflow['mapping_counts'],
            })
    assert row_checks == 8498 and len(statuses)==24
    output = {'scope':'Secondary held-out fixed workflow grid; native labels require independent same-input identity/cache proof. All other hierarchy rows explicitly mapped.','combined_results_sha256':file_sha(result_path),'identity_cache_audit_sha256':file_sha(HERE/'identity-cache-audit.json'),'row_hashes_sha256':file_sha(HERE/'row-hashes.json.gz'),'verified_workflow_and_query_hashes':row_checks,'source_budget_metric_checks':audit['checks'],'model_calls':0,'rank_calls':0,'workflows':statuses}
    (HERE/'workflow-index-labels.json').write_text(json.dumps(output,indent=2)+'\n')
    paths = [p for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json']
    manifest = {'scope':'Secondary held-out stress, all fixed-grid rows and unadjusted exploratory comparisons retained. No parameter/source/profile changes or workflow promotion.','files':{str(p.relative_to(HERE)):{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in paths}}
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'files':len(paths),'manifest_sha256':file_sha(HERE/'manifest.json'),'source_budget_metric_checks':audit['checks'],'row_hash_checks':row_checks,'native_hierarchy_rows':sum(r['label']=='native-leaf-indexed-exact-ancestry' for r in statuses)}),flush=True)


if __name__=='__main__':
    main()
