"""Summarize already frozen validation artifacts; performs no inference or selection."""
from pathlib import Path
import gzip
import hashlib
import json

W = Path('/workspace/work/omnichunk-v3')
V = W / 'validation'
CASES = [('code', 'english'), ('turkish', 'multilingual'), ('code', 'multilingual'),
         ('code-files', 'multilingual'), ('code-files', 'english')]
PROFILES = ['omnichunk', 'omnichunk-prose-compact', 'omnichunk-code-compact']
FREEZE_SHA = '54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334'


def read(path):
    return json.load(gzip.open(path)) if path.suffix == '.gz' else json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


assert sha(W / 'freeze-before-validation-v3.json') == FREEZE_SHA
post = read(V / 'candidate-postprocess-summary.json')
assert post['validation_only'] and post['no_post_release_tuning']
assert len(post['comparisons']) == 441
assert sum(len(c['capacities']) for c in post['comparisons']) == 855
paired_paths = list((W / 'comparisons/validation').rglob('vs-*.json'))
assert len(paired_paths) == 441
assert sum(len(read(p)['comparisons']) for p in paired_paths) == 855
rows = []
totals = {'required_vector_records': 0, 'byte_exact_reused_records': 0,
          'new_records': 0, 'new_passage_tokens': 0, 'new_query_tokens': 0,
          'actual_encoder_calls': 0, 'actual_encoder_seconds': 0.0,
          'frontier_groups': 0, 'rank_calls_shared_across_budgets': 0}
for domain, model in CASES:
    case = V / domain if domain == 'turkish' else V / domain / model
    candidate = case / 'candidate-final-d0'
    manifest = read(W / domain / 'validation/manifest.json')
    expected_queries = {q['query_id'] for q in manifest['queries'] if q['split'] == 'test'}
    complete = read(case / 'candidate-postprocess-complete.json')
    assert complete['status'] == 'ok' and complete['freeze'] == FREEZE_SHA
    report = read(candidate / 'report.json.gz')
    audit = read(candidate / 'cache-audit.json')
    assert {c['tool'] for c in report['candidates']} == set(PROFILES)
    assert len(report['candidates']) == 6
    assert audit['baseline_encoding_timings_not_copied']
    assert audit['maximum_input_tokens'] <= audit['max_sequence_length']
    totals['required_vector_records'] += audit['candidate_required_records']
    totals['byte_exact_reused_records'] += audit['reused_records_byte_exact']
    totals['new_records'] += audit['new_records']
    for role, stats in audit['actual_encoder_work'].items():
        totals[f'new_{role}_tokens'] += stats['new_input_tokens']
        totals['actual_encoder_calls'] += stats['encoder_calls']
        totals['actual_encoder_seconds'] += stats['encoding_seconds']
    basefront = W / 'frontier/validation' / domain
    comppath = W / 'comparisons/validation' / domain
    if domain != 'turkish':
        basefront = basefront / model
        comppath = comppath / model
    baseline_cells = {}
    for frontdir in sorted(p for p in basefront.iterdir() if p.is_dir()):
        frontier = read(frontdir / 'frontier.json')
        assert frontier['anchor_replay_exact'] and frontier['embedding_calls'] == 0
        assert frontier['requested_budgets'] == [128, 256, 512]
        totals['frontier_groups'] += 1
        totals['rank_calls_shared_across_budgets'] += frontier['rank_calls_shared_across_budgets']
        if frontdir.name != 'candidate-final-d0':
            for cell in read(frontdir / 'budget-512.report.json')['candidates']:
                key = cell['tool'], cell['chunk_capacity']
                assert key not in baseline_cells
                baseline_cells[key] = {'tool': key[0], 'capacity': key[1], 'chunks': cell['chunks'],
                    **cell['summary']['all']['evidence_at_budget']}
    primary = []
    for cell in report['candidates']:
        assert cell['status'] == 'ok'
        assert cell['max_payload_size'] <= cell['chunk_capacity']
        assert {q['query_id'] for q in cell['per_query']} == expected_queries
        assert len(cell['per_query']) == cell['summary']['all']['queries'] == len(expected_queries)
        comparisons = {}
        for f in sorted((comppath / '512' / cell['tool']).glob('vs-*.json')):
            paired = read(f)
            for cp in paired['comparisons']:
                if cp['chunk_capacity'] != cell['chunk_capacity']:
                    continue
                all_slice = cp['slices']['all']
                assert all_slice['queries'] == len(expected_queries)
                assert all_slice['gold_source_clusters'] == (60 if domain == 'turkish' else 16)
                comparisons[paired['baseline_tool']] = all_slice['metrics']
        primary.append({'tool': cell['tool'], 'capacity': cell['chunk_capacity'],
            'chunks': cell['chunks'], 'payload_utf8_bytes': cell['payload_utf8_bytes'],
            'max_payload_size': cell['max_payload_size'], 'chunk_seconds_median': cell['chunk_seconds_median'],
            'evidence_at_budget': cell['summary']['all']['evidence_at_budget'],
            'paired_metrics_512': comparisons})
    rows.append({'domain': domain, 'model': model, 'queries': len(expected_queries),
        'clusters': 60 if domain == 'turkish' else 16,
        'report_gzip_sha256': sha(candidate / 'report.json.gz'),
        'cache_audit': str(candidate / 'cache-audit.json'),
        'cache_prior_sha256': audit['prior_artifact_sha256'],
        'candidate_vector_sha256': audit['candidate_vectors_gzip_sha256'],
        'successful_baselines_512': list(baseline_cells.values()), 'primary_512': primary,
        'paired_files': len(complete['comparisons']),
        'paired_capacity_comparisons': sum(len(c['capacities']) for c in complete['comparisons'])})
assert totals['required_vector_records'] == totals['byte_exact_reused_records'] + totals['new_records']
assert totals['new_query_tokens'] == 0
assert totals['frontier_groups'] == 13
result = {'freeze_sha256': FREEZE_SHA, 'runtime_harness_commit': 'd0bd4b5ea10ff458313a82b3340c8f1a3f49e572',
    'no_post_release_tuning': True, 'primary_budget': 512, 'all_frontier_budgets': [128, 256, 512],
    'paired_files': 441, 'paired_capacity_comparisons': 855, 'bootstrap_samples': 2000, 'bootstrap_seed': 0,
    'timing_scope': 'Actual new encoding only; cached baseline encoding timings are not attributed to candidates. Chunk timings and frontier replay timings have their original scopes and include shared CPU contention.',
    'interpretation': 'All frozen profiles and successful baseline cells retained. Descriptive results; intervals are unadjusted for multiple comparisons. Isolated-code and full-file questions are correlated views. Failed baseline conformance cells remain explicit in the separate baseline audit, without successful aggregate scores.',
    'resource_totals': totals, 'cases': rows}
target = V / 'candidate-results-summary.json'
assert not target.exists(), 'Preserve existing output'
target.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
print(json.dumps({'path': str(target), 'sha256': sha(target), 'totals': totals}, indent=2))
