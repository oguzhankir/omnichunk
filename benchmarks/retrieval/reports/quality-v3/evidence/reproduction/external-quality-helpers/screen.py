"""Development-only screening with the existing frozen real-model harness."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/workspace/omnichunk')
WORK = Path(__file__).resolve().parent
OLD = Path('/workspace/work/omnichunk-dense')
MODEL = Path((OLD / 'model-path.txt').read_text().strip())
MODEL_SHA = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'


def run(command, env, log):
    with log.open('w') as output:
        subprocess.run([sys.executable, *command], cwd=ROOT, env=env,
                       stdout=output, stderr=subprocess.STDOUT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--label', required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.checkout, text=True).strip()
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=args.checkout, text=True).strip()
    out = WORK / 'screen' / args.label
    assert not out.exists(), 'Preserve prior screening evidence'
    out.mkdir(parents=True)
    env = {**os.environ, 'PYTHONPATH': str(args.checkout / 'src'), 'OMP_NUM_THREADS': '2',
           'MKL_NUM_THREADS': '2', 'TOKENIZERS_PARALLELISM': 'false', 'PYTHONHASHSEED': '0',
           'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'HF_HOME': '/workspace/work/cache/huggingface', 'XDG_CACHE_HOME': '/workspace/work/cache'}
    rows = []
    for corpus in ('corpus_v1', 'corpus_squad_v1'):
        output = out / corpus
        output.mkdir()
        common = ['--corpus', str(ROOT / 'benchmarks/retrieval' / corpus), '--split', 'dev',
                  '--tools', 'omnichunk', '--chunk-sizes', '64', '96', '--unit', 'tokens',
                  '--tokenizer', str(MODEL), '--include-special-tokens']
        vectors = output / 'vectors.json'
        report = output / 'report.json'
        print(f'{args.label}: preparing {corpus}', flush=True)
        run(['benchmarks/prepare_dense.py', *common, '--model-dir', str(MODEL),
             '--model-id', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2',
             '--model-revision', MODEL_SHA, '--batch-size', '32', '--cpu-threads', '2',
             '--output', str(vectors)], env, output / 'prepare.log')
        run(['benchmarks/run_retrieval.py', *common, '--retriever', 'dense', '--dense-embeddings',
             str(vectors), '--retrieval-budget', '512', '--top-k', '5', '--repeats', '3',
             '--require-all', '--output', str(report)], env, output / 'evaluate.log')
        for label, baseline in [('current', OLD / f'dev2-{corpus}' / 'candidate.report.json.gz'),
                                ('release', OLD / f'dev2-{corpus}' / 'baseline.report.json.gz')]:
            run(['benchmarks/compare_retrieval.py', '--baseline', str(baseline), '--candidate',
                 str(report), '--output', str(output / f'{label}-paired.json')], env,
                output / f'{label}-paired.log')
        data = json.loads(report.read_text())
        assert data['environment']['runtime_git_revision'] == revision
        assert data['environment']['runtime_git_dirty'] is False
        assert len(data['candidates']) == 2
        for row in data['candidates']:
            assert row['status'] == 'ok' and row['max_payload_size'] <= row['chunk_capacity']
            assert all(0 <= q['budget_used'] <= 512 for q in row['per_query'])
            rows.append({'corpus': corpus, 'capacity': row['chunk_capacity'], 'chunks': row['chunks'],
                         'summary': row['summary'], 'chunk_seconds': row['chunk_seconds_median']})
        with vectors.open('rb') as source, (output / 'vectors.json.gz').open('wb') as raw:
            with gzip.GzipFile(fileobj=raw, filename='', mode='wb', mtime=0) as dest:
                import shutil
                shutil.copyfileobj(source, dest)
        vectors.unlink()
    (out / 'summary.json').write_text(json.dumps({'label': args.label, 'revision': revision,
        'screen_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'development_only': True, 'rows': rows}, indent=2) + '\n')
    print(json.dumps({'label': args.label, 'revision': revision, 'rows': rows}, indent=2), flush=True)


if __name__ == '__main__':
    main()
