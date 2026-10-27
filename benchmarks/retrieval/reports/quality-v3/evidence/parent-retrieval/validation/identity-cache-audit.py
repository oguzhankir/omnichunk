"""Independent held-out identity/cache audit; no quality scores, ranks or inference.

Run only when both report/vector pairs are complete. A missing cache key or a
native/default leaf mismatch is a diagnostic outcome, never an inference request.
"""
from __future__ import annotations

import argparse
import codecs
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/workspace/work/omnichunk-v3')
RUNTIME = ROOT/'frozen-candidate-v3'
sys.path[:0] = [str(RUNTIME), str(RUNTIME/'src')]
from benchmarks.retrieval.adapters import _passage
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.dense import text_sha256
from benchmarks.retrieval.tokenization import benchmark_counter
from omnichunk import Chunker


META_FIELDS = ('schema_version', 'corpus_manifest_sha256', 'model_id',
               'model_revision', 'preprocessing_revision', 'dimension',
               'overflow_policy')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stream_records(path):
    """Bounded JSON-record parsing with complete decompressed SHA and header."""
    digest = hashlib.sha256()
    decoder = json.JSONDecoder()
    utf8 = codecs.getincrementaldecoder('utf-8')()
    buffer = ''
    prefix = None
    with gzip.open(path, 'rb') as handle:
        def read():
            raw = handle.read(65536)
            digest.update(raw)
            return utf8.decode(raw, final=not raw)
        while True:
            if prefix is None:
                chunk = read()
                if not chunk:
                    raise ValueError('Missing top-level records array')
                buffer += chunk
                marker = '  "records": ['
                location = buffer.find(marker)
                if location < 0:
                    if len(buffer) > 2_000_000:
                        raise ValueError('Unexpected vector header')
                    continue
                prefix = buffer[:location] + '  "records": []'
                buffer = buffer[location + len(marker):]
            buffer = buffer.lstrip(' \r\n\t,')
            if buffer.startswith(']'):
                suffix = buffer[1:]
                while True:
                    chunk = read()
                    if not chunk:
                        break
                    suffix += chunk
                    if len(suffix) > 2_000_000:
                        raise ValueError('Unexpected vector footer')
                header = json.loads(prefix + suffix)
                assert header.pop('records') == []
                return {'decompressed_sha256': digest.hexdigest(), 'header': header}
            try:
                record, end = decoder.raw_decode(buffer)
            except json.JSONDecodeError:
                chunk = read()
                if not chunk:
                    raise ValueError('Truncated vector record')
                buffer += chunk
                if len(buffer) > 2_000_000:
                    raise ValueError('Unexpected oversized vector record')
                continue
            buffer = buffer[end:]
            yield record


def validate_record(record, dimension):
    assert set(record) == {'role', 'text_sha256', 'vector'}
    assert record['role'] in {'query', 'passage'}
    key = (record['role'], record['text_sha256'])
    assert len(key[1]) == 64 and set(key[1]) <= set('0123456789abcdef')
    vector = record['vector']
    assert len(vector) == dimension
    assert all(type(value) in (int, float) and math.isfinite(value) for value in vector)
    assert any(vector)
    return key


def consume(path, wanted, dimension, *, compare=None, keep=False):
    records = {} if keep else None
    keys = set()
    roles = Counter()
    wanted_found = set()
    shared_equal = set()
    iterator = stream_records(path)
    while True:
        try:
            record = next(iterator)
        except StopIteration as stop:
            result = stop.value
            break
        key = validate_record(record, dimension)
        assert key not in keys, 'Duplicate exact role/text key'
        keys.add(key)
        roles[key[0]] += 1
        if key in wanted:
            wanted_found.add(key)
        if compare is not None and key in compare:
            assert record['vector'] == compare[key]['vector'], 'Changed cached vector payload'
            shared_equal.add(key)
        if keep:
            records[key] = record
    return {**result, 'records': len(keys), 'roles': dict(roles), 'keys': keys,
            'wanted_found': wanted_found, 'shared_equal': shared_equal, 'kept': records}


def key_diagnostic(key):
    source_id, start, end, text, passage_id = key
    return {'source_id': source_id, 'start': start, 'end': end,
            'text_sha256': text_sha256(text), 'passage_id': passage_id}


def candidate_keys(candidate):
    return [(row['source_id'], row['start'], row['end'], row['text'], row['passage_id'])
            for row in candidate['passages']]


def identity(native, candidate, source_ids):
    expected = candidate_keys(candidate)
    native_set, expected_set = set(native), set(expected)
    assert len(native) == len(native_set) and len(expected) == len(expected_set)
    assert all(_passage(a, b, c, d).passage_id == e for a, b, c, d, e in expected)
    return {
        'tool': candidate['tool'],
        'capacity': candidate['chunk_capacity'],
        'native_leaf_count': len(native),
        'candidate_passage_count': len(expected),
        'full_source_range_text_passage_id_set_identical': native_set == expected_set,
        'global_order_identical': native == expected,
        'candidate_id_recipe_verified': True,
        'exact_matches': len(native_set & expected_set),
        'native_only': [key_diagnostic(key) for key in sorted(native_set - expected_set)],
        'candidate_only': [key_diagnostic(key) for key in sorted(expected_set - native_set)],
        'per_source': [
            {'source_id': source_id,
             'native_leaf_count': sum(row[0] == source_id for row in native),
             'candidate_passage_count': sum(row[0] == source_id for row in expected),
             'ordered_ids_identical':
                 [row[4] for row in native if row[0] == source_id] ==
                 [row[4] for row in expected if row[0] == source_id]}
            for source_id in source_ids],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', type=Path, default=ROOT/'code-files/validation')
    parser.add_argument('--baseline', type=Path, default=ROOT/'validation/code-files/multilingual/baseline')
    parser.add_argument('--candidate', type=Path, default=ROOT/'validation/code-files/multilingual/candidate-final-d0')
    parser.add_argument('--output', type=Path, default=HERE/'identity-cache-audit.json')
    parser.add_argument('--check-ready', action='store_true')
    args = parser.parse_args()
    locations = {'baseline': args.baseline, 'candidate-final-d0': args.candidate}
    paths = {name: {kind: location/filename for kind, filename in
                   [('report', 'report.json.gz'), ('vectors', 'vectors.json.gz')]}
             for name, location in locations.items()}
    missing_paths = [str(path) for pair in paths.values() for path in pair.values()
                     if not path.is_file() or not path.stat().st_size]
    if args.check_ready or missing_paths:
        print(json.dumps({'ready': not missing_paths, 'missing_paths': missing_paths,
                          'model_calls': 0, 'rank_calls': 0, 'metrics_computed': 0}))
        return 0 if not missing_paths else 2
    if args.output.exists():
        raise ValueError('Never replace a completed audit')
    reports = {name: json.loads(gzip.decompress(pair['report'].read_bytes()))
               for name, pair in paths.items()}
    candidate = reports['candidate-final-d0']
    manifest = json.loads((args.corpus/'manifest.json').read_text())
    document_splits = sorted({row['split'] for row in manifest['documents']})
    query_splits = sorted({row['split'] for row in manifest['queries']})
    assert document_splits == query_splits and len(document_splits) == 1
    split = document_splits[0]
    corpus = load_corpus(args.corpus)
    assert all(report['corpus_manifest_sha256'] == corpus.manifest_hash for report in reports.values())
    docs = [doc for doc in corpus.documents if doc.split == split]
    queries = [query for query in corpus.queries if query.split == split]
    count = lru_cache(maxsize=100_000)(benchmark_counter('tokens', candidate['configuration']['tokenizer'], include_special_tokens=True))
    native_by_capacity = {}
    canonical_checks = 0
    for capacity in [64, 96]:
        native = []
        for doc in docs:
            tree = Chunker(size_unit='tokens', tokenizer=count, context_mode='none', coverage_policy='retrieval').hierarchical_chunk(doc.path, doc.text, source_id=doc.source_id, levels=[capacity, 128, 256, 512])
            for leaf in tree.leaves():
                start, end = leaf.byte_range.start, leaf.byte_range.end
                assert doc.text.encode('utf-8')[start:end].decode('utf-8') == leaf.text
                assert count(leaf.text) <= capacity
                passage = _passage(doc.source_id, start, end, leaf.text)
                native.append((passage.source_id, passage.start, passage.end, passage.text, passage.passage_id))
                canonical_checks += 2
        native_by_capacity[capacity] = native
    candidates = {(row['tool'], row['chunk_capacity']): row for row in candidate['candidates'] if row['status'] == 'ok'}
    identity_rows = []
    missing_candidate_profiles = []
    for tool in ['omnichunk', 'omnichunk-prose-compact', 'omnichunk-code-compact']:
        for capacity, native in native_by_capacity.items():
            selected = candidates.get((tool, capacity))
            if selected is None:
                missing_candidate_profiles.append({'tool': tool, 'capacity': capacity})
            else:
                identity_rows.append(identity(native, selected, [doc.source_id for doc in docs]))
    native_passage_keys = {('passage', text_sha256(row[3]))
                           for native in native_by_capacity.values() for row in native}
    query_keys = {('query', text_sha256(query.text)) for query in queries}
    wanted = native_passage_keys | query_keys
    dense = {name: report['configuration']['dense_embeddings'] for name, report in reports.items()}
    for field in META_FIELDS:
        assert dense['baseline'][field] == dense['candidate-final-d0'][field], field
    assert dense['baseline']['producer_metadata']['model_files'] == dense['candidate-final-d0']['producer_metadata']['model_files']
    stats = {}
    stats['candidate-final-d0'] = consume(paths['candidate-final-d0']['vectors'], wanted, dense['candidate-final-d0']['dimension'], keep=True)
    stats['baseline'] = consume(paths['baseline']['vectors'], wanted, dense['baseline']['dimension'], compare=stats['candidate-final-d0']['kept'])
    for name, stat in stats.items():
        assert stat['decompressed_sha256'] == dense[name]['artifact_sha256'], name
        assert stat['records'] == dense[name]['records']
        for field in META_FIELDS:
            assert stat['header'][field] == dense[name][field], (name, field)
        assert stat['header']['producer_metadata']['model_files'] == dense[name]['producer_metadata']['model_files']
    shared = stats['baseline']['keys'] & stats['candidate-final-d0']['keys']
    assert shared == stats['baseline']['shared_equal']
    candidate_missing = wanted - stats['candidate-final-d0']['wanted_found']
    union_missing = wanted - (stats['baseline']['wanted_found'] | stats['candidate-final-d0']['wanted_found'])
    defaults = [row for row in identity_rows if row['tool'] == 'omnichunk']
    default_identical = len(defaults) == 2 and all(row['full_source_range_text_passage_id_set_identical'] for row in defaults)
    diagnostics = []
    if not default_identical:
        diagnostics.append('native-default-leaf-identity-differs; raw default ranks cannot be labelled native hierarchy ranks without an independent frozen-vector ranking audit')
    if candidate_missing:
        diagnostics.append('candidate-cache-misses-native-leaves-or-queries; use no native-indexed quality claim from candidate ranks')
    if union_missing:
        diagnostics.append('union-cache-incomplete; native-indexed workflow is cache-infeasible with these artifacts; no inference performed')
    if not diagnostics:
        diagnostics.append('native-default-index-input-identity-and-complete-frozen-cache-verified; existing default ranks can serve as native hierarchy anchor ranks with zero additional model or ranking calls')
    result = {
        'scope': 'Independent secondary held-out native hierarchy input/cache audit; no quality scores or ranks computed',
        'script_sha256': sha(Path(__file__)),
        'runtime': str(RUNTIME),
        'runtime_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=RUNTIME, text=True).strip(),
        'corpus': str(args.corpus),
        'corpus_manifest_sha256': corpus.manifest_hash,
        'split': split,
        'documents': len(docs),
        'queries': len(queries),
        'levels': '[capacity,128,256,512]',
        'chunker_kwargs': {'size_unit': 'tokens', 'tokenizer': 'report native including special tokens', 'context_mode': 'none', 'coverage_policy': 'retrieval'},
        'passage_id_recipe': 'benchmark _passage SHA256 of source_id NUL start NUL end NUL text; no hierarchy prefix',
        'canonical_byte_and_capacity_checks': canonical_checks,
        'identity': identity_rows,
        'unavailable_candidate_profiles': missing_candidate_profiles,
        'native_default_leaf_sets_identical': default_identical,
        'native_leaf_counts': {str(capacity): len(native) for capacity, native in native_by_capacity.items()},
        'wanted_records': len(wanted),
        'wanted_roles': dict(Counter(role for role, _ in wanted)),
        'report_metadata_equal_fields': list(META_FIELDS),
        'model_files_identical_across_reports_and_artifact_headers': True,
        'shared_record_keys': len(shared),
        'all_shared_raw_vector_payloads_exactly_equal': True,
        'shared_vector_payload_equality_checks': len(stats['baseline']['shared_equal']),
        'all_wanted_in_candidate_alone': not candidate_missing,
        'candidate_missing_records': len(candidate_missing),
        'candidate_missing_keys': [list(key) for key in sorted(candidate_missing)],
        'union_missing_records': len(union_missing),
        'union_missing_keys': [list(key) for key in sorted(union_missing)],
        'diagnostics': diagnostics,
        'integrity_passed': True,
        'model_calls': 0,
        'rank_calls': 0,
        'metrics_computed': 0,
        'artifacts': {},
    }
    for name, stat in stats.items():
        result['artifacts'][name] = {
            'path': str(paths[name]['vectors']),
            'compressed_sha256': sha(paths[name]['vectors']),
            'decompressed_sha256': stat['decompressed_sha256'],
            'expected_report_decompressed_sha256': dense[name]['artifact_sha256'],
            'report_path': str(paths[name]['report']),
            'report_compressed_sha256': sha(paths[name]['report']),
            'header': stat['header'],
            'records': stat['records'],
            'roles': stat['roles'],
            'wanted_present': len(stat['wanted_found']),
            'wanted_missing': len(wanted - stat['wanted_found']),
        }
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items()
                      if key not in {'identity', 'artifacts', 'candidate_missing_keys', 'union_missing_keys'}}, indent=2))
    print('output_sha256', sha(args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
