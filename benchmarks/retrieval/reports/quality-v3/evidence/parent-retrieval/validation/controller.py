"""Run the unchanged secondary validation grid after primary artifacts exist."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
INPUTS = Path('/workspace/work/omnichunk-v3/validation/code-files/multilingual')


def main():
    required = [INPUTS/name/'report.json.gz' for name in ['baseline','candidate-final-d0','baseline-valid-96']]
    required.append(INPUTS/'failures/chonkie-sentence-64/report.json')
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        print(json.dumps({'ready':False,'missing':missing}),flush=True)
        return 75
    for name in ['baseline','candidate-final-d0']:
        directory = HERE/name
        if (directory/'results.json.gz').exists():
            print(json.dumps({'preserved_completed':name}),flush=True)
            continue
        with (directory/'study.log').open('x') as log:
            subprocess.run([sys.executable,str(directory/'study.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
    if not (HERE/'supplement-results.json.gz').exists():
        with (HERE/'supplement-controls.log').open('x') as log:
            subprocess.run([sys.executable,str(HERE/'supplement_controls.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
    if not (HERE/'combined-results.json.gz').exists():
        with (HERE/'analyze-full-inventory.log').open('x') as log:
            subprocess.run([sys.executable,str(HERE/'analyze-full-inventory.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
    if not (HERE/'row-hashes.json.gz').exists():
        subprocess.run([sys.executable,str(HERE/'hash_rows.py')],check=True)
    output = HERE/'execution.json'
    if output.exists():
        raise ValueError('Preserve existing completed execution')
    output.write_text(json.dumps({'completed_utc':datetime.now(timezone.utc).isoformat(),'scope':'Secondary fixed-grid held-out stress execution, using completed primary reports only.','model_calls':0,'rank_calls':0,'parameter_source_changes':False},indent=2)+'\n')
    print(json.dumps({'ready':True,'completed':True,'output':str(HERE)}),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
