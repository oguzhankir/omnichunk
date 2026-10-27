"""DEV-only exact native hierarchy cache coverage; no scoring or inference."""
from __future__ import annotations

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
from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
from benchmarks.retrieval.dense import text_sha256
from omnichunk import Chunker


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stream_records(path):
    """Yield one record at a time and return header plus complete decompressed SHA.

    Producers use a pretty-printed top-level ``records`` array. The bounded
    record parser preserves all other header/footer metadata and validates JSON.
    A UTF-8 incremental decoder avoids splitting a multibyte header string.
    """
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
                    raise ValueError('Missing record array')
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


def main():
    output = HERE/'cache-coverage.json'
    if output.exists():
        raise ValueError('Never replace a completed audit')
    reports = {}
    report_paths = {}
    for name in ['baseline', 'candidate-final-c1']:
        path = ROOT/'dev/code-files/multilingual'/name/'report.json.gz'
        reports[name] = json.loads(gzip.decompress(path.read_bytes()))
        report_paths[name] = path
    candidate = reports['candidate-final-c1']
    corpus = load_corpus(ROOT/'code-files/development')
    assert corpus.manifest_hash == candidate['corpus_manifest_sha256']
    identity = json.loads((HERE/'identity-audit.json').read_text())
    assert identity['candidate_report_sha256'] == sha(report_paths['candidate-final-c1'])
    assert all(row['full_source_range_text_id_set_identical'] for row in identity['capacities'])
    count = lru_cache(maxsize=100_000)(benchmark_counter('tokens', candidate['configuration']['tokenizer'], include_special_tokens=True))
    passage_keys = set()
    leaf_keys = set()
    leaf_counts = {}
    for capacity in [64, 96]:
        selected = next(row for row in candidate['candidates'] if row['tool'] == 'omnichunk' and row['chunk_capacity'] == capacity)
        passage_keys.update(('passage', text_sha256(row['text'])) for row in selected['passages'])
        leaves = 0
        for doc in corpus.documents:
            if doc.split != 'dev':
                continue
            tree = Chunker(size_unit='tokens', tokenizer=count, context_mode='none', coverage_policy='retrieval').hierarchical_chunk(doc.path, doc.text, source_id=doc.source_id, levels=[capacity, 128, 256, 512])
            for leaf in tree.leaves():
                leaf_keys.add(('passage', text_sha256(leaf.text)))
                leaves += 1
        assert leaves == selected['chunks']
        leaf_counts[str(capacity)] = leaves
    assert passage_keys == leaf_keys
    query_keys = {('query', text_sha256(query.text)) for query in corpus.queries if query.split == 'dev'}
    wanted = passage_keys | query_keys
    assert len(wanted) == 2216
    old = json.loads((HERE.parent/'native-cache-coverage.json').read_text())
    old_missing = {tuple(key) for key in old['missing_keys']}
    assert old_missing <= wanted and len(old_missing) == 718
    fields = ['schema_version', 'corpus_manifest_sha256', 'model_id', 'model_revision', 'preprocessing_revision', 'dimension', 'overflow_policy']
    dense = {name: report['configuration']['dense_embeddings'] for name, report in reports.items()}
    for field in fields:
        assert dense['baseline'][field] == dense['candidate-final-c1'][field], field
    assert dense['baseline']['producer_metadata']['model_files'] == dense['candidate-final-c1']['producer_metadata']['model_files']
    stats = {}
    paths = {name: ROOT/'dev/code-files/multilingual'/name/'vectors.json.gz' for name in reports}
    stats['candidate-final-c1'] = consume(paths['candidate-final-c1'], wanted, dense['candidate-final-c1']['dimension'], keep=True)
    stats['baseline'] = consume(paths['baseline'], wanted, dense['baseline']['dimension'], compare=stats['candidate-final-c1']['kept'])
    for name, result in stats.items():
        expected = dense[name]
        assert result['decompressed_sha256'] == expected['artifact_sha256'], name
        assert result['records'] == expected['records']
        for field in fields:
            assert result['header'][field] == expected[field], (name, field)
        assert result['header']['producer_metadata']['model_files'] == expected['producer_metadata']['model_files']
    assert stats['baseline']['header']['producer_metadata']['model_files'] == stats['candidate-final-c1']['header']['producer_metadata']['model_files']
    baseline_missing = wanted - stats['baseline']['wanted_found']
    assert baseline_missing == old_missing
    shared = stats['baseline']['keys'] & stats['candidate-final-c1']['keys']
    assert stats['baseline']['shared_equal'] == shared
    candidate_missing = wanted - stats['candidate-final-c1']['wanted_found']
    union_missing = wanted - (stats['baseline']['wanted_found'] | stats['candidate-final-c1']['wanted_found'])
    result = {
        'scope': 'DEV-only exact native hierarchy/default candidate vector cache integrity; no score or rank computation',
        'script_sha256': sha(Path(__file__)),
        'identity_audit_sha256': sha(HERE/'identity-audit.json'),
        'original_native_protocol_sha256': sha(HERE.parent/'native-protocol.json'),
        'previous_coverage_sha256': sha(HERE.parent/'native-cache-coverage.json'),
        'runtime': str(RUNTIME),
        'runtime_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=RUNTIME, text=True).strip(),
        'corpus_manifest_sha256': corpus.manifest_hash,
        'native_leaf_counts': leaf_counts,
        'native_leaf_and_default_candidate_text_key_sets_identical': True,
        'wanted_records': len(wanted),
        'wanted_roles': dict(Counter(role for role, _ in wanted)),
        'corpus_query_count': sum(query.split == 'dev' for query in corpus.queries),
        'all_report_metadata_equal_fields': fields,
        'model_files_identical_across_reports_and_artifact_headers': True,
        'shared_record_keys': len(shared),
        'all_shared_raw_vector_payloads_exactly_equal': True,
        'shared_vector_payload_equality_checks': len(stats['baseline']['shared_equal']),
        'prior_missing_records': len(old_missing),
        'prior_missing_filled_by_candidate': len(old_missing & stats['candidate-final-c1']['keys']),
        'all_wanted_in_candidate_alone': not candidate_missing,
        'candidate_missing_records': len(candidate_missing),
        'candidate_missing_keys': [list(key) for key in sorted(candidate_missing)],
        'union_missing_records': len(union_missing),
        'union_missing_keys': [list(key) for key in sorted(union_missing)],
        'model_calls': 0,
        'rank_calls': 0,
        'metrics_computed': 0,
        'artifacts': {},
    }
    for name, stat in stats.items():
        result['artifacts'][name] = {
            'path': str(paths[name]),
            'compressed_sha256': sha(paths[name]),
            'decompressed_sha256': stat['decompressed_sha256'],
            'expected_report_decompressed_sha256': dense[name]['artifact_sha256'],
            'report_path': str(report_paths[name]),
            'report_compressed_sha256': sha(report_paths[name]),
            'header': stat['header'],
            'records': stat['records'],
            'roles': stat['roles'],
            'wanted_present': len(stat['wanted_found']),
            'wanted_missing': len(wanted - stat['wanted_found']),
        }
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'artifacts'}, indent=2))
    print('output_sha256', sha(output))


if __name__ == '__main__':
    main()
