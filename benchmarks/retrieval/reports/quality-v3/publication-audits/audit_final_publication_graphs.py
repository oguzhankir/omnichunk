"""Verify publication graphs against frozen ledgers and rendered artist geometry."""
from collections import Counter
from pathlib import Path
import csv
import gzip
import hashlib
import json
import math
import os
import runpy
import sys
import xml.etree.ElementTree as ET

W = Path('/workspace/work/omnichunk-v3')
H = W / 'frozen-candidate-v3'
D = W / 'drafts'
sys.path[:0] = [str(H / 'src'), str(H)]
os.environ['MPLBACKEND'] = 'Agg'
from benchmarks.retrieval.tokenization import benchmark_counter
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from matplotlib.markers import MarkerStyle
from matplotlib.colors import to_rgba
import numpy as np
from PIL import Image, ImageChops

checks = Counter()
inputs = {}


def sha(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def bind(p):
    inputs[str(p.relative_to(W))] = sha(p)


def read(p):
    bind(p)
    with (gzip.open(p, 'rt') if p.suffix == '.gz' else p.open()) as f:
        return json.load(f)


def verify(value, label):
    assert value, label
    checks[label] += 1


def close(x, y):
    return math.isclose(float(x), float(y), rel_tol=0, abs_tol=1e-12)


def csvrows(p):
    bind(p)
    with p.open(newline='') as f:
        return list(csv.DictReader(f))


freeze = read(W / 'freeze-before-validation-v3.json')
verify(inputs['freeze-before-validation-v3.json'] == '54f2d64ede52854e41f9dffaa4235f0eb991f3bc8df1031916754dbac188a334', 'freeze_binding')
choices = read(W / 'reference-choices-before-validation.json')['choices']
verify(inputs['reference-choices-before-validation.json'] == freeze['reference_choices_sha256'], 'prevalidation_reference_binding')
summary = read(W / 'validation/candidate-results-summary.json')
audit = read(D / 'plot-audit.json')
plot_script = W / 'plot_validation_final.py'
bind(plot_script)
verify(audit['script_sha256'] == inputs['plot_validation_final.py'], 'plot_source_binding')
for name, digest in audit['inputs'].items():
    verify(sha(W / name) == digest, 'plot_input_binding')
for name, digest in audit['outputs'].items():
    bind(D / name)
    verify(inputs['drafts/' + name] == digest, 'plot_output_binding')
for name in ['primary-reference-forest-preview.png', 'validation-quality-workload-preview.png']:
    bind(D / name)
for name, digest in [
    ('validation-candidate-artifact-audit.json', '2ef41777931c758a1e71a4ed6a7a4f13ddc0e88a6729db7066c18c0c57cbfa3d'),
    ('validation-candidate-projection-audit.json', '20b02956e09eb2551aed414e49afb19f34c6cded1de956b65a29bc981e15111c'),
    ('validation-baseline-artifact-audit.json', '924deedb5fd4d091a315ee467fe538bb909a21f9fcee624099131243fcb9eb39')]:
    bind(W / 'adapter-audit' / name)
    verify(inputs['adapter-audit/' + name] == digest, 'raw_ledger_audit_binding')

order = [('turkish', 'multilingual'), ('code', 'multilingual'), ('code', 'english'),
         ('code-files', 'multilingual'), ('code-files', 'english')]
labels = {('turkish', 'multilingual'): 'Turkish passages / multilingual',
          ('code', 'multilingual'): 'Python functions / multilingual',
          ('code', 'english'): 'Python functions / English',
          ('code-files', 'multilingual'): 'Original Python files / multilingual',
          ('code-files', 'english'): 'Original Python files / English'}
colors = {'omnichunk': '#2166ac', 'omnichunk-prose-compact': '#e08214',
          'omnichunk-code-compact': '#1b9e77'}
raw = {}
ordered_raw = []
for domain, model in order:
    case = W / 'validation' / domain
    if domain != 'turkish':
        case /= model
    for group in ['baseline', 'baseline-valid-96', 'candidate-final-d0']:
        p = case / group / 'report.json.gz'
        if not p.exists():
            continue
        report = read(p)
        count = benchmark_counter('tokens', report['configuration']['tokenizer'], include_special_tokens=True)
        workloads = report['configuration']['dense_embeddings']['producer_metadata']['candidate_workloads']
        verify(report['configuration']['retrieval_budget'] == 512, 'primary_budget_scope')
        for cell in report['candidates']:
            verify(cell['status'] == 'ok', 'successful_plot_cell')
            role = 'candidate' if group == 'candidate-final-d0' else 'baseline'
            key = domain, model, role, cell['tool'], cell['chunk_capacity']
            verify(key not in raw, 'raw_point_unique_key')
            work = next(w for w in workloads if (w['tool'], w['chunk_capacity'])
                        == (cell['tool'], cell['chunk_capacity']))
            native = sum(count(p['text']) for p in cell['passages'])
            unique = sum(count(t) for t in {p['text'] for p in cell['passages']})
            verify(native == work['passage_input_tokens'] and unique == work['unique_passage_input_tokens'],
                   'native_complete_and_unique_workload_recount')
            verify(cell['chunks'] == len(cell['passages']), 'vector_count_recount')
            for metric in ['recall', 'precision']:
                mean = sum(q['evidence_at_budget'][metric] for q in cell['per_query']) / len(cell['per_query'])
                verify(close(mean, cell['summary']['all']['evidence_at_budget'][metric]), 'quality_mean_recount')
            point = {'domain': domain, 'model': model, 'role': role, 'tool': cell['tool'],
                     'capacity': cell['chunk_capacity'], 'recall': cell['summary']['all']['evidence_at_budget']['recall'],
                     'precision': cell['summary']['all']['evidence_at_budget']['precision'],
                     'vectors': cell['chunks'], 'native_passage_tokens': native,
                     'unique_native_passage_tokens': unique, 'report_sha256': sha(p)}
            raw[key] = point
            ordered_raw.append(point)
verify(len(raw) == 125, 'complete_125_successful_points')
points = csvrows(D / 'validation-quality-workload.csv')
seen = set()
for point in points:
    key = point['domain'], point['model'], point['role'], point['tool'], int(point['capacity'])
    verify(key in raw and key not in seen, 'csv_workload_unique_raw_key')
    seen.add(key)
    expected = raw[key]
    for label in ['vectors', 'native_passage_tokens', 'unique_native_passage_tokens']:
        verify(int(point[label]) == expected[label], 'csv_workload_integer_value')
    for label in ['recall', 'precision']:
        verify(close(point[label], expected[label]), 'csv_workload_quality_value')
    verify(point['report_sha256'] == expected['report_sha256'], 'csv_workload_report_binding')
verify(set(raw) == seen and len(points) == 125, 'csv_workload_no_omission')

primary = csvrows(D / 'primary-reference-points.csv')
verify(len(primary) == len(choices) == 10, 'ten_primary_reference_points')
for row in primary:
    domain, model, cap = row['domain'], row['model'], int(row['capacity'])
    choice = next(c for c in choices if (c['domain'], c['model'], c['chunk_capacity']) == (domain, model, cap))
    verify(row['profile'] == choice['candidate_profile'] and row['reference'] == choice['named_reference'],
           'primary_frozen_profile_reference_labels')
    candidate = raw[domain, model, 'candidate', row['profile'], cap]
    reference = raw[domain, model, 'baseline', row['reference'], cap]
    pair = W / 'comparisons/validation' / domain
    if domain != 'turkish':
        pair /= model
    pair /= '512'
    pair /= row['profile']
    pair /= 'vs-' + row['reference'] + '.json'
    stored = next(c for c in read(pair)['comparisons'] if c['chunk_capacity'] == cap)['slices']['all']['metrics']['recall']
    for label, expected in [('recall', candidate['recall']), ('reference_recall', reference['recall']),
                            ('delta', stored['mean_delta']), ('ci_low', stored['bootstrap_delta_ci_95'][0]),
                            ('ci_high', stored['bootstrap_delta_ci_95'][1]),
                            ('vector_ratio', candidate['vectors'] / reference['vectors'])]:
        verify(close(row[label], expected), 'primary_raw_point_and_interval')
    verify(int(row['vectors']) == candidate['vectors'] and int(row['reference_vectors']) == reference['vectors'],
           'primary_raw_vector_counts')
verify([(r['domain'], r['model'], int(r['capacity'])) for r in primary]
       == [(d, m, c) for d, m in order for c in [64, 96]], 'primary_display_order')

# Re-render only to a new audit directory, preserving every original artifact.
render = W / 'adapter-audit/final-graph-audit-render'
verify(not render.exists(), 'audit_render_no_overwrite')
saved = []
original_savefig = Figure.savefig


def capture(figure, fname, *args, **kwargs):
    if str(fname).endswith('.svg'):
        saved.append(figure)
    return original_savefig(figure, fname, *args, **kwargs)


Figure.savefig = capture
os.environ['OMNICHUNK_V3_EVIDENCE'] = str(W)
os.environ['OMNICHUNK_PLOT_OUTPUT'] = str(render)
try:
    runpy.run_path(str(plot_script), run_name='__main__')
finally:
    Figure.savefig = original_savefig
verify(len(saved) == 2, 'two_graph_figures')
for name in ['primary-reference-points.csv', 'primary-reference-forest.svg',
             'validation-quality-workload.csv', 'validation-quality-workload.svg']:
    verify(sha(render / name) == sha(D / name), 'original_csv_svg_exact_regeneration')
for name in ['primary-reference-forest-preview.png', 'validation-quality-workload-preview.png']:
    difference = ImageChops.difference(Image.open(render / name).convert('RGBA'), Image.open(D / name).convert('RGBA'))
    verify(difference.getbbox() is None, 'preview_pixel_exact_regeneration')

forest, workload = saved
ax, bx = forest.axes
verify(len(ax.containers) == 10 and len(bx.texts) == 10, 'forest_ten_errorbars_and_ratios')
for y, (row, container) in enumerate(zip(primary, ax.containers)):
    delta, low, high = [float(row[k]) * 100 for k in ['delta', 'ci_low', 'ci_high']]
    xdata, ydata = container.lines[0].get_data()
    verify(close(xdata[0], delta) and close(ydata[0], y), 'forest_delta_coordinate')
    segment = container.lines[2][0].get_segments()[0]
    verify(np.allclose(segment, [[low, y], [high, y]], rtol=0, atol=1e-12), 'forest_ci_endpoint_coordinates')
    expected_color = '#18784a' if low > 0 else '#b2182b' if high < 0 else '#586875'
    verify(container.lines[0].get_color() == expected_color, 'forest_ci_sign_color')
    ratio_x, ratio_y = bx.lines[y].get_data()
    verify(close(ratio_x[0], row['vector_ratio']) and close(ratio_y[0], y), 'forest_vector_ratio_coordinate')
    verify(bx.lines[y].get_color() == colors[row['profile']], 'forest_ratio_profile_color')
    verify(bx.texts[y].get_text().strip() == f"{row['vectors']}/{row['reference_vectors']}", 'forest_vector_annotation')
    verify(ax.get_xlim()[0] < low <= delta <= high < ax.get_xlim()[1]
           and bx.get_xlim()[0] < float(row['vector_ratio']) < bx.get_xlim()[1], 'forest_no_data_clipping')
verify([t.get_text() for t in ax.get_yticklabels()]
       == [f"{labels[(r['domain'], r['model'])]} | {r['capacity']}" for r in primary], 'forest_cohort_capacity_labels')
verify(ax.get_xlabel() == 'Recall difference (percentage points)'
       and bx.get_xlabel() == 'Index vector ratio\ncandidate / frozen named reference', 'forest_axis_semantics')

svg = ET.fromstring((D / 'validation-quality-workload.svg').read_bytes())
svg_groups = [g for g in svg.iter('{http://www.w3.org/2000/svg}g')
              if g.attrib.get('id', '').startswith('PathCollection_')]
verify(len(svg_groups) == 125, 'svg_125_data_artists')
svg_artist = 0
for axis, key in zip(workload.axes[:5], order):
    subset = sorted([p for p in ordered_raw if (p['domain'], p['model']) == key], key=lambda p: p['role'] == 'candidate')
    verify(len(axis.collections) == len(subset), 'panel_complete_point_artists')
    verify(axis.get_title() == labels[key] and axis.get_ylim() == (0.0, 1.0)
           and axis.get_xlabel() == 'Native passage tokens (thousands)'
           and axis.get_ylabel() == 'Evidence recall', 'workload_panel_labels_and_scale')
    for point, collection in zip(subset, axis.collections):
        x, y = point['native_passage_tokens'] / 1000, point['recall']
        verify(np.allclose(collection.get_offsets(), [[x, y]], rtol=0, atol=1e-12), 'workload_artist_raw_coordinate')
        expected_color = colors[point['tool']] if point['role'] == 'candidate' else '#111111' if point['tool'] == 'fixed' else '#aaaaaa'
        expected_alpha = .85 if point['role'] == 'candidate' or point['tool'] == 'fixed' else .55
        verify(np.allclose(collection.get_facecolors()[0], to_rgba(expected_color, expected_alpha), rtol=0, atol=1e-12),
               'workload_artist_role_profile_color')
        marker = MarkerStyle('o' if point['capacity'] == 64 else '^')
        shape = marker.get_path().transformed(marker.get_transform())
        verify(np.array_equal(collection.get_paths()[0].vertices, shape.vertices), 'workload_marker_capacity_semantics')
        verify(close(collection.get_sizes()[0], 34 if point['role'] == 'candidate' or point['tool'] == 'fixed' else 18),
               'workload_marker_role_size')
        verify(axis.get_xlim()[0] < x < axis.get_xlim()[1] and 0 <= y <= 1, 'workload_no_data_clipping')
        pixel = axis.transData.transform((x, y))
        expected_svg = [pixel[0] * 72 / workload.dpi, workload.get_figheight() * 72 - pixel[1] * 72 / workload.dpi]
        use = next(svg_groups[svg_artist].iter('{http://www.w3.org/2000/svg}use'))
        verify(np.allclose([float(use.attrib['x']), float(use.attrib['y'])], expected_svg, rtol=0, atol=2e-5),
               'all_svg_marker_transform_coordinates')
        svg_artist += 1
verify(svg_artist == 125, 'all_svg_points_verified')
legend = workload.axes[5].get_legend()
verify([t.get_text() for t in legend.get_texts()] == ['Final structural profile', 'Final prose compact',
       'Final code compact', 'Fixed control', 'Prior main and named strategies', '64-token children', '96-token children'],
       'complete_role_profile_capacity_legend')
text = '\n'.join(t.get_text() for t in workload.texts)
verify('Within-panel comparisons only' in text and 'identical profiles overlap' in text
       and 'five failed baseline cells' in text and 'not elapsed-time or Pareto claims' in text,
       'scope_overlap_failure_workload_disclosures')
verify('not general leadership' in '\n'.join(t.get_text() for t in forest.texts), 'no_universal_leadership_disclosure')

for name, digest in inputs.items():
    verify(sha(W / name) == digest, 'inputs_unchanged_during_audit')
target = W / 'adapter-audit/final-publication-graph-audit.json'
verify(not target.exists(), 'audit_result_no_overwrite')
result = {'status': 'passed_with_presentation_notes', 'checks': sum(checks.values()),
          'checks_by_kind': dict(checks), 'audit_source_sha256': sha(Path(__file__)), 'inputs': inputs,
          'coverage': {'primary_reference_points': 10, 'successful_workload_points': 125,
                       'svg_marker_coordinates_verified': 125, 'exactly_regenerated_csv_svg_files': 4,
                       'pixel_identical_png_previews': 2},
          'findings': [],
          'presentation_notes': [
              'Identical structural/prose points overlap and can occlude blue markers; caption explicitly discloses overlap, all125 data artists/CSV records remain present.',
              'Forest right markers use profile colors, while forest left interval colors encode CI sign. Profile text and separate axes explain the panels; a dedicated profile-color key would improve standalone clarity.',
              'Forest rows identify cohort/model/capacity but not each named reference. Exact references are in the companion CSV and frozen reference table; add names if distributing the SVG by itself.'],
          'visual_review': 'Both original PNG previews inspected through view_image: titles, labels, footnotes and data fit canvas; five cohort panels plus legend; no visible clipping or omitted cohort; no universal or Pareto leadership implied.',
          'scope': 'All plotted CSV fields validated against frozen raw reports/workload token recounts and frozen primary reference comparison CIs; all125 source quality means recounted. Captured artists match raw points, markers, colors, axes and bounds. SVG/CSV outputs regenerated byte-exact in a separate audit directory, PNG previews pixel-exact,125 exported SVG coordinates independently transformed and checked. Original artifacts unchanged.',
          'limitations': 'Graph audit does not create new encoder outputs or quality settings. Existing independent raw candidate/baseline and statistical audits provide underlying metric/model provenance. Candidate profiles and named references were selected before validation; intervals are unadjusted descriptive evidence and correlated models/views are not independent.'}
target.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'status': result['status'], 'checks': result['checks'], 'path': str(target),
                  'sha256': sha(target), 'coverage': result['coverage']}, indent=2), flush=True)
