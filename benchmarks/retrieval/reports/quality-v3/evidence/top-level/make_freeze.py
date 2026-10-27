from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys

W=Path('/workspace/work/omnichunk-v3')
R=W/'frozen-candidate'
sys.path.insert(0,str(R))
from benchmarks.prepare_dense import model_files

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=R,text=True).strip()
def manifest(paths,base):return {str(p.relative_to(base)):sha(p) for p in sorted(paths) if p.is_file()}

if git('status','--porcelain'):raise ValueError('Dirty runtime/harness freeze')
out=W/'freeze-before-validation.json'
if out.exists():raise ValueError('Preserve previous freeze')
models=[]
for meta_path in [Path('/workspace/work/omnichunk-dense/model-path.txt'),W.parent/'omnichunk-quality/new-corpus/second-model/model-path.txt']:
 p=Path(meta_path.read_text().strip());models.append({'directory':str(p),'revision':p.name,'files':model_files(p)})
protocol=json.loads((W/'protocol.json').read_text())
record={'schema_version':1,'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'runtime_and_harness_commit':git('rev-parse','HEAD'),'runtime_src_git_tree':git('rev-parse','HEAD:src/omnichunk'),'runtime_files':manifest((R/'src/omnichunk').rglob('*'),R/'src/omnichunk'),'harness_files':manifest(list((R/'benchmarks').glob('*.py'))+list((R/'benchmarks/retrieval').glob('*.py')),R),'models':models,'protocol':protocol,'installed_packages_sha256':sha(W/'environment/installed-package-hashes.json'),'development_manifests':{name:sha(W/name/'development/manifest.json') for name in ['turkish','code','code-files']},'validation_commitments':{name:json.loads((W/name/file).read_text()) for name,file in [('turkish','commitment.json'),('code','validation-commitment.json'),('code-files','validation-commitment.json')]},'profiles':{'omnichunk':{},'omnichunk-prose-compact':{'prose_boundary_policy':'compact'},'omnichunk-code-compact':{'code_boundary_policy':'compact'}},'preserved_optional_markdown_policy':'pack is experimental cost tradeoff; not selected as general primary profile','views':'Individual-function code remains primary; original-file code is correlated same-query supplemental stress view, predeclared before file-view scores. Turkish is question-only passage retrieval.','reference_selection':'For each domain/model/capacity choose named competitor by development 512-token recall, then precision, then fewer vectors, then stable tool-name. Fixed control is always separately reported; all strategies and budgets reported, including failures. Selection must never read validation scores.','validation_policy':'Source/model/settings fixed; no selection or quality tuning after validation release. Native overflow/conformance failures are retained, never repaired or silently dropped.','timing_scope':'Concurrent development jobs; encoder/chunker elapsed figures retained diagnostically, no isolated speed or end-to-end latency claim.','tests':json.loads((W/'final-runtime-gates.json').read_text()),'review_gate':'Completed code/security reviews for this source head must be recorded in review-before-validation.json before custodian release.'}
# Do not fingerprint transient Python bytecode as runtime source.
record['runtime_files']={k:v for k,v in record['runtime_files'].items() if '__pycache__' not in k and not k.endswith('.pyc')}
out.write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'freeze':str(out),'sha256':sha(out),'runtime_commit':record['runtime_and_harness_commit']}))
