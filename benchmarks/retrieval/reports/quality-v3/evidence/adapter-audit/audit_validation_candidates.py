"""Independent, inference-free audit of the frozen validation candidate artifacts."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from pathlib import Path
import gc
import gzip
import hashlib
import json
import math
import random
import sys

import numpy as np

W = Path('/workspace/work/omnichunk-v3')
H = W / 'frozen-candidate-v3'
sys.path[:0] = [str(H / 'src'), str(H)]
from omnichunk.retrieval_eval import EvidenceSpan, score_evidence, score_ranking
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter

FREEZE = '54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334'
BASE_AUDIT = '924deedb5fd4d091a315ee467fe538bb909a21f9fcee624099131243fcb9eb39'
PRODUCER = '805f796a40c2eace68da44e4be987cec901a39c9af75f1b76ba5ee26e2c7bd97'
CASES = [('code', 'english'), ('turkish', 'multilingual'), ('code', 'multilingual'),
         ('code-files', 'multilingual'), ('code-files', 'english')]
PROFILES = {'omnichunk', 'omnichunk-prose-compact', 'omnichunk-code-compact'}
checks = Counter()
jobs = []
counts = Counter()


def verify(condition, label):
    assert condition, label
    checks[label] += 1


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    with (gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()) as f:
        return json.load(f)


def raw_sha(path):
    digest = hashlib.sha256()
    with gzip.open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value, allow_nan=False, separators=(',', ':')).encode()


def normal(vector):
    scale = max(abs(x) for x in vector)
    verify(scale > 0 and all(math.isfinite(x) for x in vector), 'finite_nonzero_vector')
    scaled = tuple(x / scale for x in vector)
    norm = math.hypot(*scaled)
    return tuple(x / norm for x in scaled)


def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-12)


freeze_path = W / 'freeze-before-validation-v3.json'
verify(sha(freeze_path) == FREEZE, 'freeze_binding')
freeze = read(freeze_path)
runtime = freeze['runtime_and_harness_commit']
for name, digest in freeze['harness_files'].items():
    verify(sha(H / name) == digest, 'harness_file_binding')
for name, digest in freeze['runtime_files'].items():
    verify(sha(H / 'src/omnichunk' / name) == digest, 'runtime_file_binding')
verify(sha(W / 'extend_dense_vectors.py') == PRODUCER, 'external_producer_binding')
verify(sha(W / 'adapter-audit/validation-baseline-artifact-audit.json') == BASE_AUDIT,
       'shared_baseline_audit_binding')
baseline_audit = read(W / 'adapter-audit/validation-baseline-artifact-audit.json')
verify(baseline_audit['status'] == 'passed' and baseline_audit['successful_cells'] == 95
       and baseline_audit['explicit_failure_cells'] == 5, 'baseline_complete_scope')

for domain, model in CASES:
    case = W / 'validation' / domain
    front = W / 'frontier/validation' / domain
    if domain != 'turkish':
        case /= model
        front /= model
    source = case / 'candidate-final-d0'
    report = read(source / 'report.json.gz')
    vectors = read(source / 'vectors.json.gz')
    job = read(source / 'job.json')
    expected_manifest = freeze['validation_commitments'][domain].get(
        'validation_manifest_sha256', freeze['validation_commitments'][domain].get('manifest_sha256'))
    corpus = load_corpus(W / domain / 'validation')
    docs = {d.source_id: d.text.encode('utf-8') for d in corpus.documents}
    queries = {q.query_id: q for q in corpus.queries}
    verify(corpus.manifest_hash == report['corpus_manifest_sha256']
           == vectors['corpus_manifest_sha256'] == expected_manifest, 'manifest_binding')
    environment = report['environment']
    verify(environment['git_revision'] == environment['runtime_git_revision'] == runtime
           and environment['runtime_matches_checkout'] and not environment['dirty_checkout']
           and not environment['runtime_git_dirty'], 'actual_frozen_runtime')
    verify(job['runtime'] == runtime and job['freeze_sha256'] == FREEZE, 'job_freeze_binding')
    config = report['configuration']
    verify(config['split'] == 'test' and config['unit'] == 'tokens'
           and config['include_special_tokens'] and config['retrieval_budget'] == 512
           and config['top_k'] == 5 and config['repeats'] == 3
           and config['context'] == 'none' and config['overlap'] == 0, 'frozen_settings')
    counter = benchmark_counter('tokens', config['tokenizer'], include_special_tokens=True)
    embed = config['dense_embeddings']
    verify(raw_sha(source / 'vectors.json.gz') == embed['artifact_sha256'], 'vector_artifact_binding')
    md = vectors['producer_metadata']
    frozen_model = next(m for m in freeze['models'] if m['revision'] == vectors['model_revision'])
    verify(md['model_files'] == md['prior_model_files'] == frozen_model['files'], 'model_snapshot_binding')
    verify(vectors['overflow_policy'] == 'error' and vectors['preprocessing_revision']
           == 'sentence-transformers-no-prompt-v1' and md['prompt'] == ''
           and md['include_special_tokens'] and md['device'] == 'cpu'
           and md['maximum_input_tokens'] <= md['max_sequence_length'], 'native_encoder_contract')
    verify(md['external_producer_source_sha256'] == PRODUCER
           and md['frozen_producer_source_sha256'] == freeze['harness_files']['benchmarks/prepare_dense.py']
           and 'timings' not in md, 'producer_and_timing_scope')
    prior_path = Path(job['prior_artifact'])
    verify(sha(prior_path) == md['prior_artifact_sha256'] == job['prior_artifact_sha256'],
           'compressed_prior_binding')
    prior = read(prior_path)
    for key in ['model_id', 'model_revision', 'preprocessing_revision', 'dimension', 'overflow_policy',
                'corpus_manifest_sha256']:
        verify(prior[key] == vectors[key], 'prior_vector_contract')
    for key in ['model_files', 'packages', 'prompt', 'max_sequence_length', 'supported_pipeline',
                'device', 'input_policy', 'normalization']:
        verify(prior['producer_metadata'][key] == md[key], 'prior_encoder_contract')
    prior_records = {(r['role'], r['text_sha256']): r['vector'] for r in prior['records']}
    verify(len(prior_records) == len(prior['records']) == md['prior_artifact_records'], 'prior_unique_role_keys')
    records = {(r['role'], r['text_sha256']): r['vector'] for r in vectors['records']}
    verify(len(records) == len(vectors['records']), 'candidate_unique_role_keys')
    for key, vector in records.items():
        verify(key[0] in ['query', 'passage'] and len(vector) == vectors['dimension'] == 384,
               'role_vector_dimension')
    texts = {('query', text_sha(q.text)): q.text for q in queries.values()}
    for candidate in report['candidates']:
        for p in candidate['passages']:
            texts['passage', text_sha(p['text'])] = p['text']
    verify(set(records) == set(texts), 'exact_required_vector_inputs')
    reused = []
    actual = {role: {'reused_texts': 0, 'new_texts': 0, 'reused_input_tokens': 0,
                     'new_input_tokens': 0, 'requested_input_tokens': 0}
              for role in ['query', 'passage']}
    for key, vector in records.items():
        role, digest = key
        tokens = counter(texts[key])
        verify(tokens <= md['max_sequence_length'], 'all_required_inputs_native_fit')
        actual[role]['requested_input_tokens'] += tokens
        if key in prior_records:
            verify(canonical(vector) == canonical(prior_records[key]), 'reused_vector_payload_exact')
            reused.append([role, digest, hashlib.sha256(canonical(vector)).hexdigest()])
            actual[role]['reused_texts'] += 1
            actual[role]['reused_input_tokens'] += tokens
        else:
            actual[role]['new_texts'] += 1
            actual[role]['new_input_tokens'] += tokens
    verify(hashlib.sha256(canonical(sorted(reused))).hexdigest() == md['reused_vector_payloads_sha256'],
           'reused_payload_manifest')
    for role, values in actual.items():
        declared = md['actual_encoder_work'][role]
        for key, value in values.items():
            verify(value == declared[key], 'actual_encoder_work_accounting')
        verify(declared['requested_unique_texts'] == values['reused_texts'] + values['new_texts'],
               'role_request_cardinality')
        verify(sum(declared['encoder_batch_sizes']) == values['new_texts']
               and len(declared['encoder_batch_sizes']) == declared['encoder_calls'], 'actual_batch_accounting')
        verify(declared['encoding_seconds'] >= 0, 'actual_encoding_duration')
    verify(actual['query']['new_texts'] == 0
           and md['actual_encoder_work']['query']['encoder_calls'] == 0, 'zero_query_encoding')
    counts['records'] += len(records)
    counts['reused'] += len(reused)
    counts['new'] += len(records) - len(reused)
    del prior, prior_records
    normalized = {key: normal(vector) for key, vector in records.items()}
    del records, vectors
    verify({(c['tool'], c['chunk_capacity']) for c in report['candidates']}
           == {(t, cap) for t in PROFILES for cap in [64, 96]}, 'profile_capacity_coverage')
    for c in report['candidates']:
        verify(c['status'] == 'ok' and c['embedding_calls'] == 0, 'successful_inference_free_cell')
        counts['cells'] += 1
        pmap = {p['passage_id']: p for p in c['passages']}
        verify(len(pmap) == len(c['passages']) == c['chunks'], 'passage_count_and_unique_ids')
        ends = {}
        sizes = []
        for p in c['passages']:
            raw = docs[p['source_id']]
            start, end = p['start'], p['end']
            prev = ends.get(p['source_id'], 0)
            verify(0 <= prev <= start < end <= len(raw) and not raw[prev:start].decode('utf-8').strip(),
                   'source_order_and_nonwhitespace_coverage')
            verify(raw[start:end].decode('utf-8') == p['text'], 'canonical_utf8_source_slice')
            sizes.append(counter(p['text']))
            verify(sizes[-1] <= c['chunk_capacity'], 'native_payload_budget')
            ends[p['source_id']] = end
        for sid, raw in docs.items():
            verify(not raw[ends.get(sid, 0):].decode('utf-8').strip(), 'source_tail_coverage')
        verify(c['payload_utf8_bytes'] == sum(len(p['text'].encode('utf-8')) for p in c['passages'])
               and c['max_payload_size'] == max(sizes), 'reported_payload_cost')
        verify(len(c['per_query']) == len(queries)
               and {r['query_id'] for r in c['per_query']} == set(queries), 'complete_query_ids')
        for row in c['per_query']:
            q = queries[row['query_id']]
            verify(row['query'] == q.text, 'exact_query_text')
            selected = [pmap[i] for i in row['budget_passage_ids']]
            used = counter('\n\n'.join(p['text'] for p in selected)) if selected else 0
            verify(used == row['budget_used'] and used <= 512, 'joined_native_context_budget')
            scores = asdict(score_evidence([EvidenceSpan(p['source_id'], p['start'], p['end']) for p in selected], q.evidence))
            verify(scores == row['evidence_at_budget'], 'evidence_at_budget_recalculated')
            ranks = [pmap[p['passage_id']] for p in row['ranks']]
            verify(asdict(score_evidence([EvidenceSpan(p['source_id'], p['start'], p['end']) for p in ranks], q.evidence))
                   == row['evidence_at_k'], 'evidence_at_k_recalculated')
            qrels = {p['passage_id']: 1.0 for p in c['passages'] if any(
                p['source_id'] == e.source_id and max(p['start'], e.start) < min(p['end'], e.end)
                for e in q.evidence)}
            verify(asdict(score_ranking([p['passage_id'] for p in ranks], qrels, k=5)) == row['ranking'],
                   'top5_ranking_metrics_recalculated')
            qv = normalized['query', text_sha(q.text)]
            recorded_order = []
            for item, p in zip(row['ranks'], ranks):
                verify(all(item[k] == p[k] for k in ['passage_id', 'source_id', 'start', 'end']),
                       'ranked_passage_binding')
                pv = normalized['passage', text_sha(p['text'])]
                cosine = max(-1.0, min(1.0, math.fsum(a * b for a, b in zip(qv, pv))))
                verify(close(cosine, item['score']), 'recorded_cosine_recalculated')
                recorded_order.append((-item['score'], item['passage_id']))
            verify(recorded_order == sorted(recorded_order), 'recorded_top5_order')
        for metric in ['precision', 'recall', 'iou']:
            verify(close(sum(r['evidence_at_budget'][metric] for r in c['per_query']) / len(queries),
                         c['summary']['all']['evidence_at_budget'][metric]), 'aggregate_mean_recalculated')
    # Bind every frontier to its original artifact and compare all primary rows exactly.
    for directory in sorted(p for p in front.iterdir() if p.is_dir()):
        original = case / directory.name
        frontier = read(directory / 'frontier.json')
        verify(frontier['source_report_file_sha256'] == sha(original / 'report.json.gz')
               and frontier['source_vectors_file_sha256'] == sha(original / 'vectors.json.gz'), 'frontier_source_binding')
        verify(frontier['embedding_calls'] == 0 and frontier['requested_budgets'] == [128, 256, 512],
               'frontier_inference_free_contract')
        anchor = read(directory / 'budget-512.report.json')
        original_report = report if directory.name == 'candidate-final-d0' else read(original / 'report.json.gz')
        verify(anchor['candidates'] == original_report['candidates'], 'all512_anchor_cells_exact')
        for out in frontier['outputs']:
            verify(sha(directory / out['file']) == out['sha256'], 'frontier_output_binding')
        counts['frontier_groups'] += 1
        counts['shared_rank_calls'] += frontier['rank_calls_shared_across_budgets']
    jobs.append({'domain': domain, 'model': model, 'cells': 6, 'queries': len(queries),
                 'records': sum(a['reused_texts'] + a['new_texts'] for a in actual.values()),
                 'reused': len(reused), 'new': sum(a['new_texts'] for a in actual.values()),
                 'report_sha256': sha(source / 'report.json.gz'),
                 'vectors_sha256': sha(source / 'vectors.json.gz')})
    print('candidate audit complete', domain, model, flush=True)
    del report, normalized, texts, original_report, anchor
    gc.collect()

# Independent vectorized bootstrap reconstruction for every stored paired slice.
# Random draws follow the declared seed, while multiplicity-matrix arithmetic is
# independent of the comparison implementation's nested Python summation.
draws_cache = {}
report_cache = {}
for domain, model in CASES:
    prefix = W / 'comparisons/validation' / domain
    front = W / 'frontier/validation' / domain
    case = W / 'validation' / domain
    if domain != 'turkish':
        prefix /= model
        front /= model
        case /= model
    manifest = read(W / domain / 'validation/manifest.json')
    qcluster = {}
    docgroups = {d['source_id']: d['repository'] for d in manifest['documents']} if domain != 'turkish' else {}
    for q in manifest['queries']:
        groups = {e['source_id'] if domain == 'turkish' else docgroups[e['source_id']] for e in q['evidence']}
        verify(len(groups) == 1, 'gold_query_single_predeclared_group')
        qcluster[q['query_id']] = next(iter(groups))
    for pair_path in sorted(prefix.rglob('vs-*.json')):
        paired = read(pair_path)
        budget = int(pair_path.parent.parent.name)
        verify(paired['bootstrap']['samples'] == 2000 and paired['bootstrap']['seed'] == 0,
               'paired_bootstrap_contract')
        expected_manifest = freeze['validation_commitments'][domain].get(
            'validation_manifest_sha256', freeze['validation_commitments'][domain].get('manifest_sha256'))
        verify(paired['corpus_manifest_sha256'] == expected_manifest,
               'paired_manifest_contract')
        if domain != 'turkish':
            verify(paired['bootstrap']['cluster_map']['groups'] == 16, 'repository_cluster_count')
        report_paths = [front / p / f'budget-{budget}.report.json' for p in ['baseline', 'baseline-valid-96']]
        bpath = next(p for p in report_paths if p.exists() and any(
            c['tool'] == paired['baseline_tool'] for c in read(p)['candidates']))
        cpath = front / 'candidate-final-d0' / f'budget-{budget}.report.json'
        for p in [bpath, cpath]:
            if p not in report_cache:
                report_cache[p] = read(p)
        before = {(c['tool'], c['chunk_capacity']): c for c in report_cache[bpath]['candidates']}
        after = {(c['tool'], c['chunk_capacity']): c for c in report_cache[cpath]['candidates']}
        verify(paired['reports']['baseline_sha256'] == sha(bpath), 'paired_baseline_report_binding')
        for comparison in paired['comparisons']:
            cap = comparison['chunk_capacity']
            left = {r['query_id']: r for r in before[paired['baseline_tool'], cap]['per_query']}
            right = {r['query_id']: r for r in after[paired['candidate_tool'], cap]['per_query']}
            verify(set(left) == set(right) == set(qcluster), 'paired_complete_query_join')
            for label, stored in comparison['slices'].items():
                ids = sorted(q for q in left if label == 'all' or label.startswith('language:')
                             and left[q]['language'] == label.split(':', 1)[1]
                             or label.startswith('category:') and left[q]['category'] == label.split(':', 1)[1])
                groups = sorted({qcluster[q] for q in ids})
                verify(len(ids) == stored['queries'] and len(groups) == stored['gold_source_clusters'],
                       'paired_slice_group_counts')
                cache_key = len(groups)
                if cache_key not in draws_cache:
                    rng = random.Random(0)
                    draws = np.zeros((2000, len(groups)), dtype=np.int64)
                    for row in range(2000):
                        for _ in groups:
                            draws[row, rng.randrange(len(groups))] += 1
                    draws_cache[cache_key] = draws
                draws = draws_cache[cache_key]
                group_ids = [[q for q in ids if qcluster[q] == g] for g in groups]
                denominators = draws @ np.array([len(g) for g in group_ids], dtype=np.float64)
                for metric, values in stored['metrics'].items():
                    a = [left[q]['evidence_at_budget'][metric] for q in ids]
                    b = [right[q]['evidence_at_budget'][metric] for q in ids]
                    delta = {q: right[q]['evidence_at_budget'][metric] - left[q]['evidence_at_budget'][metric] for q in ids}
                    verify(close(sum(a) / len(ids), values['baseline_mean'])
                           and close(sum(b) / len(ids), values['candidate_mean'])
                           and close(sum(delta.values()) / len(ids), values['mean_delta']), 'paired_means_recalculated')
                    verify(sum(x > 1e-12 for x in delta.values()) == values['wins']
                           and sum(abs(x) <= 1e-12 for x in delta.values()) == values['ties']
                           and sum(x < -1e-12 for x in delta.values()) == values['losses'], 'paired_win_tie_loss_recalculated')
                    sums = np.array([sum(delta[q] for q in group) for group in group_ids])
                    boot = (draws @ sums) / denominators
                    interval = np.quantile(boot, [0.025, 0.975], method='linear')
                    verify(all(close(x, y) for x, y in zip(interval, values['bootstrap_delta_ci_95'])),
                           'paired_all_bootstrap_intervals_recalculated')
            counts['paired_capacity_comparisons'] += 1
        counts['paired_files'] += 1
    print('paired audit complete', domain, model, flush=True)
    report_cache.clear()
    gc.collect()

verify(counts['cells'] == 30 and counts['frontier_groups'] == 13
       and counts['shared_rank_calls'] == 9008 and counts['paired_files'] == 441
       and counts['paired_capacity_comparisons'] == 855, 'final_coverage')
target = W / 'adapter-audit/validation-candidate-artifact-audit.json'
verify(not target.exists(), 'no_overwrite_audit')
result = {'status': 'passed', 'freeze_sha256': FREEZE, 'runtime_and_harness_commit': runtime,
          'shared_baseline_audit_sha256': BASE_AUDIT,
          'audit_source_sha256': sha(Path(__file__)), 'checks': sum(checks.values()),
          'checks_by_kind': dict(checks), 'coverage': dict(counts), 'jobs': jobs,
          'scope': 'All candidate native source slices/budgets/query IDs/evidence/top5 metrics/means; exact role+text cache payload reuse/miss accounting; recorded top5 cosine values/order; all source512 frontier cells exact; all441 paired files and855 capacity comparisons including independent multiplicity-matrix recomputation of every stored clustered bootstrap interval. No encoder calls or new quality settings.',
          'limitations': 'Does not independently rerun neural encoders or prove the external producer used declared model weights; producer integrity tests and pinned baseline snapshot provenance are separate. Does not recompute global nearest-neighbor ordering against omitted passages; recorded top5 scores/order and exact frozen frontier anchors are checked. Intervals remain descriptive, unadjusted for multiple comparisons and assume independent declared source/repository groups. Isolated-code/full-file question views are correlated.'}
target.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'status': result['status'], 'checks': result['checks'], 'coverage': dict(counts),
                  'path': str(target), 'sha256': sha(target)}, indent=2), flush=True)
