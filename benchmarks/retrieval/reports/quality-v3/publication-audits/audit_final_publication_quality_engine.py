"""Independent semantic review of published v3 numeric tables and raw ledgers."""
from pathlib import Path
import csv
import datetime
import gzip
import hashlib
import json
import re
import subprocess

W = Path('/workspace/work/omnichunk-v3')
P = Path('/workspace/omnichunk/benchmarks/retrieval/reports/quality-v3')
D = W / 'drafts'
H = W / 'frozen-candidate-v3'
INPUTS = {}
CHECKS = []
CACHE = {}


def sha(path):
    raw = path.read_bytes()
    value = hashlib.sha256(raw).hexdigest()
    INPUTS[str(path)] = {'sha256': value, 'bytes': len(raw)}
    return value


def read(path):
    if path not in CACHE:
        sha(path)
        raw = path.read_bytes()
        CACHE[path] = json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)
    return CACHE[path]


def check(label, actual, expected):
    assert actual == expected, (label, actual, expected)
    CHECKS.append({'label': label, 'actual': actual, 'expected': expected})


def numeric(label, actual, expected):
    assert abs(float(actual) - float(expected)) <= 1e-12, (label, actual, expected)
    CHECKS.append({'label': label, 'actual': actual, 'expected': expected})


def tables(text):
    result = []
    for block in re.findall(r'(?:^\|.*\n)+', text, re.M):
        lines = [line.strip() for line in block.strip().splitlines()]
        result.append([[cell.strip() for cell in line.strip('|').split('|')] for line in lines])
    return result


def interval(metric):
    lo, hi = metric['bootstrap_delta_ci_95']
    return f"{metric['mean_delta']:+.6f} [{lo:+.6f}, {hi:+.6f}]"


def wtl(metric):
    return '/'.join(str(metric[k]) for k in ['wins', 'ties', 'losses'])


def key(label):
    domain, model, cap = [x.strip() for x in label.split('/')]
    return domain, {'ML': 'multilingual', 'EN': 'english'}[model], int(cap)


def casepath(domain, model):
    case = W / 'validation' / domain
    return case if domain == 'turkish' else case / model


def metrics(cell):
    return cell['summary']['all']['evidence_at_budget']


NAMES = {'default': 'omnichunk', 'prose-compact': 'omnichunk-prose-compact', 'code-compact': 'omnichunk-code-compact'}
CASES = [('turkish', 'multilingual'), ('code', 'multilingual'), ('code', 'english'),
         ('code-files', 'multilingual'), ('code-files', 'english')]
RAW = {}
for domain, model in CASES:
    case = casepath(domain, model)
    candidate_report = read(case / 'candidate-final-d0/report.json.gz')
    candidate = {(c['tool'], c['chunk_capacity']): c for c in candidate_report['candidates']}
    workloads = {(r['tool'], r['chunk_capacity']): r for r in candidate_report['configuration']['dense_embeddings']['producer_metadata']['candidate_workloads']}
    baseline = {}
    for path in sorted(case.glob('baseline*/report.json.gz')):
        for cell in read(path)['candidates']:
            k = cell['tool'], cell['chunk_capacity']
            assert k not in baseline
            baseline[k] = cell
    RAW[domain, model] = candidate, baseline, workloads


def paired(domain, model, profile, capacity, reference):
    path = W / 'comparisons/validation' / domain
    if domain != 'turkish':
        path = path / model
    paths = list((path / '512' / profile).glob(f'vs-{reference}*.json'))
    found = []
    for p in paths:
        data = read(p)
        if data['baseline_tool'] != reference:
            continue
        found.extend(c['slices']['all']['metrics']['recall'] for c in data['comparisons'] if c['chunk_capacity'] == capacity)
    assert len(found) == 1
    return found[0]


freeze = read(W / 'freeze-before-validation-v3.json')
check('freeze_sha256', sha(W / 'freeze-before-validation-v3.json'), '54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334')
check('frozen_commit', subprocess.check_output(['git', '-C', str(H), 'rev-parse', 'HEAD'], text=True).strip(), freeze['runtime_and_harness_commit'])
check('frozen_worktree_clean', subprocess.check_output(['git', '-C', str(H), 'status', '--porcelain=v1'], text=True), '')
for path, expected in freeze['runtime_files'].items():
    check('runtime_file:' + path, sha(H / 'src/omnichunk' / path), expected)
    check('publication_runtime_file:' + path, sha(Path('/workspace/omnichunk/src/omnichunk') / path), expected)
for path, expected in freeze['harness_files'].items():
    check('harness_file:' + path, sha(H / path), expected)
    check('publication_harness_file:' + path, sha(Path('/workspace/omnichunk') / path), expected)

references = read(W / 'reference-choices-before-validation.json')
check('reference_choices_frozen_hash', sha(W / 'reference-choices-before-validation.json'), freeze['reference_choices_sha256'])
reference_map = {(r['domain'], r['model'], r['chunk_capacity']): r for r in references['choices']}
published = (P / 'README.md').read_text()
draft = (D / 'README-final.md').read_text()
sha(P / 'README.md')
sha(D / 'README-final.md')
check('all_118_table_lines_unchanged', [x for x in published.splitlines() if x.startswith('|')], [x for x in draft.splitlines() if x.startswith('|')])
check('118_markdown_table_lines', sum(x.startswith('|') for x in published.splitlines()), 118)
formatting = read(P / 'publication-formatting.json')
check('formatting_original_binding', formatting['original_reviewed_draft_sha256'], sha(D / 'README-final.md'))
check('formatting_published_binding', formatting['published_readme_sha256'], sha(P / 'README.md'))
for name, expected in formatting['direct_artifacts'].items():
    check('direct_artifact:' + name, sha(P / name), expected)

found = {'primary_reference': 0, 'fixed_observed': 0, 'default_prior': 0, 'all_profiles': 0, 'context': 0, 'parent': 0}
for table in tables(published):
    header, body = table[0], table[2:]
    if header[0] == 'View / encoder / capacity':
        for row in body:
            domain, model, capacity = key(row[0])
            candidate, baseline, work = RAW[domain, model]
            ref = reference_map[domain, model, capacity]
            compact = candidate[ref['candidate_profile'], capacity]
            tag = f'{domain}/{model}/{capacity}'
            if header[1] == 'Frozen candidate':
                found['primary_reference'] += 1
                check(tag + ':primary_profile', NAMES[row[1]], ref['candidate_profile'])
                check(tag + ':reference_identity', row[3], ref['named_reference'])
                check(tag + ':primary_recall', row[2], f"{metrics(compact)['recall']:.6f}")
                check(tag + ':reference_recall', row[4], f"{metrics(baseline[ref['named_reference'], capacity])['recall']:.6f}")
                pair = paired(domain, model, ref['candidate_profile'], capacity, ref['named_reference'])
                check(tag + ':primary_interval', row[5], interval(pair))
                check(tag + ':primary_wtl', row[6], wtl(pair))
            elif header[1] == 'Fixed recall':
                found['fixed_observed'] += 1
                fixed = baseline['fixed', capacity]
                best_name, best = max(((name, cell) for (name, cap), cell in baseline.items() if cap == capacity and name not in {'fixed', 'omnichunk'}), key=lambda item: (metrics(item[1])['recall'], metrics(item[1])['precision'], -item[1]['chunks'], item[0]))
                check(tag + ':fixed_recall', row[1], f"{metrics(fixed)['recall']:.6f}")
                check(tag + ':fixed_interval', row[2], interval(paired(domain, model, ref['candidate_profile'], capacity, 'fixed')))
                check(tag + ':observed_best_identity_recall', row[3], f"{best_name}: {metrics(best)['recall']:.6f}")
                check(tag + ':observed_best_interval', row[4], interval(paired(domain, model, ref['candidate_profile'], capacity, best_name)))
                check(tag + ':vectors_triple', row[5], f"{compact['chunks']} / {fixed['chunks']} / {best['chunks']}")
            elif header[1] == 'Prior Omni recall → final default':
                found['default_prior'] += 1
                old = baseline['omnichunk', capacity]
                cell = candidate['omnichunk', capacity]
                check(tag + ':default_recall', row[1], f"{metrics(old)['recall']:.6f} → {metrics(cell)['recall']:.6f}")
                check(tag + ':default_prior_interval', row[2], interval(paired(domain, model, 'omnichunk', capacity, 'omnichunk')))
                check(tag + ':default_vectors', row[3], f"{old['chunks']} → {cell['chunks']}")
                check(tag + ':default_precision_iou', row[4], f"{metrics(cell)['precision']:.6f} / {metrics(cell)['iou']:.6f}")
            elif header[1] == 'Profile':
                found['all_profiles'] += 1
                profile = NAMES[row[1]]
                cell = candidate[profile, capacity]
                for pos, metric in [(2, 'recall'), (3, 'precision'), (4, 'iou')]:
                    check(tag + ':' + profile + ':' + metric, row[pos], f"{metrics(cell)[metric]:.6f}")
                check(tag + ':' + profile + ':vectors', row[5], str(cell['chunks']))
                check(tag + ':' + profile + ':tokens', row[6], str(work[profile, capacity]['passage_input_tokens']))
            else:
                raise AssertionError(header)
    elif header[0] == 'Encoder':
        context = read(W / 'context-dense-development/summary.json')
        for row in body:
            model, profile = row[:2]
            low = {r['chunk_capacity']: r for r in context[model + '-128'] if r['tool'] == profile}
            high = {r['chunk_capacity']: r for r in context[model + '-512'] if r['tool'] == profile}
            check(model + ':' + profile + ':context128', row[2], ' / '.join(f"{low[cap]['summary']['recall']:.6f}" for cap in [64, 96]))
            check(model + ':' + profile + ':context512', row[3], ' / '.join(f"{high[cap]['summary']['recall']:.6f}" for cap in [64, 96]))
            check(model + ':' + profile + ':contexttokens', row[4], ' / '.join(str(high[cap]['payload_tokens']) for cap in [64, 96]))
            found['context'] += 1
    elif header[0] == 'Split':
        for row in body:
            root = W / ('parent-retrieval/candidate-final-c1' if row[0] == 'Development' else 'parent-retrieval/validation')
            outputs = read(root / 'combined-summary.json')['outputs']
            pairs = read(root / 'paired.json')['comparisons']
            select = lambda values, method, target: next(r for r in values if r['version'].startswith('final-') and r['tool'] == 'omnichunk' and r['capacity'] == 96 and r['method'] == method and r['expansion_target'] == target)
            check(row[0] + ':parentraw', row[1], f"{select(outputs, 'raw-prefix', 512)['summary']['recall']:.6f}")
            check(row[0] + ':window128', row[2], f"{select(outputs, 'source-window', 128)['summary']['recall']:.6f}")
            metric = select(pairs, 'source-window', 128)['versus_own_raw']['recall']
            check(row[0] + ':window_interval', row[3], interval(metric))
            check(row[0] + ':window_wtl', row[4], wtl(metric))
            found['parent'] += 1
check('semantic_table_row_counts', found, {'primary_reference': 10, 'fixed_observed': 10, 'default_prior': 10, 'all_profiles': 30, 'context': 8, 'parent': 2})

# Verify every CSV outcome against its exact bound raw report, with no omitted failures.
with (D / 'validation-outcomes.csv').open() as f:
    outcomes = list(csv.DictReader(f))
sha(D / 'validation-outcomes.csv')
check('validation_outcome_count', len(outcomes), 380)
check('validation_success_count', sum(r['status'] == 'ok' for r in outcomes), 375)
check('validation_explicit_failure_count', sum(r['status'] != 'ok' for r in outcomes), 5)
for row in outcomes:
    path = W / row['artifact']
    report = read(path)
    tag = row['artifact'] + ':' + row['tool'] + '/' + row['capacity']
    check(tag + ':csv_source_hash', row['artifact_sha256'], sha(path))
    cells = [c for c in report['candidates'] if c['tool'] == row['tool'] and c['chunk_capacity'] == int(row['capacity'])]
    check(tag + ':unique_cell', len(cells), 1)
    cell = cells[0]
    check(tag + ':csv_status', row['status'], cell['status'])
    if cell['status'] == 'ok':
        for name in ['recall', 'precision', 'iou']:
            numeric(tag + ':csv_' + name, row[name], metrics(cell)[name])
        check(tag + ':csv_vectors', int(row['vectors']), cell['chunks'])
        work = report['configuration']['dense_embeddings']['producer_metadata']['candidate_workloads']
        load = next(w for w in work if w['tool'] == row['tool'] and w['chunk_capacity'] == int(row['capacity']))
        check(tag + ':csv_native_tokens', int(row['native_passage_tokens']), load['passage_input_tokens'])
    else:
        check(tag + ':failure_no_invented_score', [row[k] for k in ['recall', 'precision', 'iou', 'vectors']], ['', '', '', ''])

# Preserve source provenance even for historic rows; do not treat numeric-token matches as semantic proof.
ledger = read(D / 'final-report-inputs.json')
for relative, expected in ledger['all_source_inputs'].items():
    check('input_ledger:' + relative, sha(W / relative), expected['sha256'])
check('input_ledger_report_binding', ledger['report_sha256'], sha(D / 'README-final.md'))
check('input_ledger_csv_binding', ledger['validation_csv_sha256'], sha(D / 'validation-outcomes.csv'))

# Historic numeric trial statements retain their correct runtime/corpus identities.
development = read(D / 'development-inputs.json')
dev_paths = {a['path']: a for a in development['artifacts']}
sha(D / 'development-outcomes.csv')
with (D / 'development-outcomes.csv').open() as f:
    dev_rows = list(csv.DictReader(f))


def historic(runtime, tool, cap, corpus='omnichunk-retrieval-v1', artifact_contains=None):
    matches = [r for r in dev_rows if r['runtime'].startswith(runtime) and r['tool'] == tool
               and r['capacity'] == str(cap) and r['retrieval_budget'] == '512'
               and (corpus is None or r['corpus_id'] == corpus)
               and (artifact_contains is None or artifact_contains in r['artifact'])]
    assert len(matches) == 1, (runtime, tool, cap, matches)
    row = matches[0]
    source = dev_paths[row['artifact']]
    path = Path(source['absolute_input'])
    report = read(path)
    check('historic_source_hash:' + row['artifact'], sha(path), row['artifact_sha256'])
    check('historic_ledger_hash:' + row['artifact'], sha(path), source['sha256'])
    cell = next(c for c in report['candidates'] if c['tool'] == tool and c['chunk_capacity'] == cap)
    numeric('historic_csv_recall:' + row['artifact'] + '/' + str(cap), row['recall'], metrics(cell)['recall'])
    check('historic_csv_vectors:' + row['artifact'] + '/' + str(cap), int(row['vectors']), cell['chunks'])
    return cell


def historical_clause(prefix, clause):
    line = next(line for line in published.splitlines() if line.startswith('| ' + prefix))
    check('historic_table:' + prefix + ':' + clause, clause in line, True)


old64 = historic('e63c7', 'omnichunk', 64)
old96 = historic('e63c7', 'omnichunk', 96)
rebalance64 = historic('e0249', 'omnichunk', 64)
rebalance96 = historic('e0249', 'omnichunk', 96)
isolated64 = historic('e78e5', 'omnichunk', 64)
historical_clause('Comment sentence rebalance', f"Original synthetic recall improves {metrics(old64)['recall']:.6f} → {metrics(rebalance64)['recall']:.6f} at 64; 96 remains {metrics(rebalance96)['recall']:.6f}.")
historical_clause('Comment isolation', f"{isolated64['chunks']} rather than {rebalance64['chunks']} synthetic 64-token vectors")
pack64 = historic('1671c', 'omnichunk-pack', 64)
pack96 = historic('1671c', 'omnichunk-pack', 96)
historical_clause('Markdown pack', f"synthetic recall {metrics(pack64)['recall']:.6f} / {metrics(pack96)['recall']:.6f} versus baseline {metrics(old64)['recall']:.6f} / {metrics(old96)['recall']:.6f}; vectors {pack64['chunks']} / {pack96['chunks']} versus {old64['chunks']} / {old96['chunks']}")
combined64 = historic('1b6238', 'omnichunk', 64)
combined96 = historic('1b6238', 'omnichunk', 96)
combined_pack64 = historic('1b6238', 'omnichunk-pack', 64)
combined_pack96 = historic('1b6238', 'omnichunk-pack', 96)
historical_clause('Combined repair', f"Structural default synthetic recall {metrics(combined64)['recall']:.6f} / {metrics(combined96)['recall']:.6f}, vectors {combined64['chunks']} / {combined96['chunks']}")
historical_clause('Combined repair', f"declines to {metrics(combined_pack64)['recall']:.6f} / {metrics(combined_pack96)['recall']:.6f} with {combined_pack64['chunks']} / {combined_pack96['chunks']} vectors")
unconditional = historic('fca224', 'omnichunk', 64)
historical_clause('Unconditional measured prose', f"Original synthetic 64 recall declines {metrics(rebalance64)['recall']:.6f} → {metrics(unconditional)['recall']:.6f}")
ast64 = historic('9e292', 'omnichunk', 64)
ast96 = historic('9e292', 'omnichunk', 96)
historical_clause('Complete AST body packing', f"original synthetic recall remains {metrics(ast64)['recall']:.6f} / {metrics(ast96)['recall']:.6f}")
compact64 = historic('2b5d', 'omnichunk-code-compact', 64, None, 'english')
compact96 = historic('2b5d', 'omnichunk-code-compact', 96, None, 'english')
historical_clause('Compact code', f"English means {metrics(compact64)['recall']:.6f} / {metrics(compact96)['recall']:.6f}")
full96 = historic('0ecb56', 'omnichunk-code-compact', 96)
historical_clause('Fuller early compact payloads', f"original synthetic 96 recall falls from structural {metrics(rebalance96)['recall']:.6f} to {metrics(full96)['recall']:.6f}")

# Dataset counts and source commitments in the corpus table/prose.
counts = {}
for domain in ['turkish', 'code', 'code-files']:
    for split in ['development', 'validation']:
        path = W / domain / split / 'manifest.json'
        manifest = read(path)
        counts[domain, split] = (len(manifest['documents']), len(manifest['queries']))
        if domain != 'turkish':
            counts[domain, split] += (len({doc['repository'] for doc in manifest['documents']}),)
check('dataset_Turkish_counts', [counts['turkish', split] for split in ['development', 'validation']], [(60, 120), (60, 120)])
check('dataset_isolated_counts', [counts['code', split] for split in ['development', 'validation']], [(64, 64, 16), (64, 64, 16)])
check('dataset_file_counts', [counts['code-files', split] for split in ['development', 'validation']], [(37, 56, 15), (35, 56, 16)])
dataset_table = next(t for t in tables(published) if t[0][0] == 'Corpus')
check('dataset_table_Turkish_counts', '60 / 60 source passages, 120 / 120 original question stems' in dataset_table[2][1], True)
check('dataset_table_isolated_counts', '64 / 64 functions and proxy queries, 16 / 16 repository clusters' in dataset_table[3][1], True)
check('dataset_table_file_counts', '37 / 35 original files, 56 / 56 existing eligible questions, 15 / 16 repository clusters' in dataset_table[4][1], True)
for domain in ['turkish', 'code', 'code-files']:
    check('validation_manifest_displayed:' + domain, sha(W / domain / 'validation/manifest.json') in published, True)
tests = freeze['tests']
check('source_gates_passed', tests['all_passed'], True)
check('source_test_counts_displayed', f"**{tests['pytest_summary']['passed']:,} tests passed, {tests['pytest_summary']['optional_skipped']} optional tests were skipped**" in published, True)
check('combined_coverage_displayed', f"**{tests['coverage']['totals']['percent_covered']:.2f}% combined statement/branch coverage" in published, True)
check('branch_only_coverage_displayed', f"approximately {tests['coverage']['totals']['percent_branches_covered']:.2f}%" in published, True)
protocol = freeze['protocol']
check('frozen_protocol_native_capacities', protocol['chunk_native_special_token_inclusive_capacities'], [64, 96])
check('frozen_protocol_primary_context', protocol['primary_retrieval_budget'], 512)
check('frozen_protocol_sensitivity_context', protocol['sensitivity_retrieval_budgets'], [128, 256])
check('frozen_protocol_rank_k', protocol['top_k_separate'], 5)
check('frozen_protocol_overlap', protocol['overlap'], 0)
check('frozen_protocol_context', protocol['derived_context'], 'none')
check('frozen_protocol_CPU_contract', [protocol[k] for k in ['torch_threads', 'torch_interop_threads', 'batch_size', 'chunking_repeats']], [2, 2, 32, 3])
context = read(W / 'context-dense-development/summary.json')
for model in ['multilingual', 'english']:
    for cap in [64, 96]:
        for budget in [128, 256, 512]:
            rows = {(r['tool'], r['chunk_capacity']): r for r in context[f'{model}-{budget}']}
            check(f'context_minimal_vs_fixed_loss:{model}/{cap}/{budget}', rows['omni-minimal-original-path', cap]['summary']['recall'] < rows['fixed-raw', cap]['summary']['recall'], True)
        rows = {(r['tool'], r['chunk_capacity']): r for r in context[f'{model}-128']}
        check(f'context_128_raw_loss:{model}/{cap}', rows['omni-minimal-original-path', cap]['summary']['recall'] < rows['omni-raw', cap]['summary']['recall'], True)

# Specific prose claims have semantic, case-scoped arithmetic checks.
candidate, baseline, _ = RAW['code', 'english']
compact = candidate['omnichunk-code-compact', 64]
fixed = baseline['fixed', 64]
semchunk = baseline['semchunk', 64]
tie = paired('code', 'english', 'omnichunk-code-compact', 64, 'fixed')
check('exact_English64_recall_tie', [tie[k] for k in ['mean_delta', 'wins', 'losses']], [0.0, 0, 0])
check('exact_English64_recall_tie_interval', tie['bootstrap_delta_ci_95'], [0.0, 0.0])
check('English64_vector_reduction_text', f"{100 * (1 - compact['chunks'] / semchunk['chunks']):.2f}% fewer" in published, True)
named = [metrics(c)['recall'] for (tool, cap), c in baseline.items() if cap == 64 and tool not in {'fixed', 'omnichunk'}]
numeric('English64_semchunk_highest_named', metrics(semchunk)['recall'], max(named))
check('English64_named_positive_interval', paired('code', 'english', 'omnichunk-code-compact', 64, 'semchunk')['bootstrap_delta_ci_95'][0] > 0, True)
for model in ['multilingual', 'english']:
    cell = RAW['code-files', model][0]['omnichunk-code-compact', 96]
    old = RAW['code-files', model][1]['omnichunk', 96]
    metric = paired('code-files', model, 'omnichunk-code-compact', 96, 'omnichunk')
    clause = f"prior OmniChunk recall {metrics(old)['recall']:.6f} → compact {metrics(cell)['recall']:.6f}; paired delta {interval(metric)}, W/T/L {wtl(metric)}."
    check(model + ':explicit_real_file_96_loss_prose', clause in published, True)
for clause in ['Broad superiority and a Pareto advantage are not established',
               'Multilingual isolated code does not establish an advantage over its strongest controls',
               'Intervals are **unadjusted', 'not independent replications',
               'Validation is now observed and must not be reused as a new unseen tuning set',
               'not a replacement for the frozen compact primary',
               'not evidence of unique general superiority']:
    check('scientific_scope:' + clause, clause in published, True)

graph_path = W / 'adapter-audit/final-publication-graph-audit.json'
graph = read(graph_path)
check('independent_graph_audit_passed', graph['status'] in {'passed', 'passed_with_presentation_notes'}, True)
check('independent_graph_numeric_findings', graph['findings'], [])
result = {
    'status': 'passed', 'recorded_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope': 'Independent semantic numeric report review against raw frozen reports/comparisons, complete final outcome CSV, input ledgers, source freeze, and separate independent plot review. No inference, runtime/profile/model/settings changes.',
    'published_report_sha256': sha(P / 'README.md'), 'original_draft_sha256': sha(D / 'README-final.md'),
    'checks': len(CHECKS), 'semantic_table_rows': found, 'csv_rows': len(outcomes),
    'independent_graph_audit': {'path': str(graph_path), 'sha256': sha(graph_path)},
    'resolved_finding': 'Original draft opening overgeneralized multilingual named-control deficit; published report correctly says no established advantage. The inherited development-prose-fill pointer and left/right plot color semantics are clarified in separate publication prose. All numeric table lines were preserved.',
    'remaining_findings': [],
    'graph_presentation_notes': graph['presentation_notes'],
    'limitations': 'This review does not rerun encoders or source tests. Previously independently audited raw candidate/baseline and bootstrap artifacts are reused as immutable evidence; this review checks semantic attribution, rounded display values, full CSV rows, provenance and publication scope. Link restoration utility and later publication-only edits require their separate final checks.',
    'checked_inputs': INPUTS, 'assertions': CHECKS,
}
result['audit_script_sha256'] = sha(Path(__file__))
target = W / 'adapter-audit/final-publication-quality-engine-audit.json'
assert not target.exists(), 'Preserve prior audit output'
target.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
print(json.dumps({'path': str(target), 'sha256': sha(target), 'checks': len(CHECKS)}, indent=2))
