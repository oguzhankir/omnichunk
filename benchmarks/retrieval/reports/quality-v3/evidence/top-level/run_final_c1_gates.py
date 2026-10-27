"""Immutable final-runtime verification evidence; all products stay outside the repository."""
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,os,re,subprocess,time
root=Path('/workspace/omnichunk');out=Path('/workspace/work/omnichunk-v3/final-gates-c1');out.mkdir(exist_ok=False)
bin=Path('/workspace/work/omnichunk-dense/venv/bin')
rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert rev.startswith('c1d2186')
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
def manifest():
 return [(p.relative_to(root/'src').as_posix(),hashlib.sha256(p.read_bytes()).hexdigest())for p in sorted((root/'src/omnichunk').rglob('*'))if p.is_file()and(p.suffix=='.py'or p.name=='py.typed')]
rows=manifest();source_hash=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
base={'runtime_commit':rev,'started_utc':datetime.now(timezone.utc).isoformat(),'source_file_sha256_rows':rows,'source_tree_sha256':source_hash,'NLTK_DATA':'/workspace/work/omnichunk-v3/adapter-audit/nltk_data','network_enabled':True,'gates':{}}
(out/'source-manifest.json').write_text(json.dumps({k:v for k,v in base.items()if k!='gates'},indent=2)+'\n')
env={**os.environ,'PYTHONPATH':str(root/'src'),'NLTK_DATA':base['NLTK_DATA'],'TOKENIZERS_PARALLELISM':'false'}
commands={
 'pytest_coverage':[str(bin/'pytest'),'-q','--cov=omnichunk','--cov-branch','--cov-report=term-missing','--cov-report=json:'+str(out/'coverage.json'),'--cov-fail-under=90'],
 'ruff_check':[str(bin/'ruff'),'check','src','tests'],
 'ruff_format':[str(bin/'ruff'),'format','--check','src','tests'],
 'strict_mypy':[str(bin/'mypy'),'--python-version','3.12','src/omnichunk'],
 'strict_mkdocs':[str(bin/'mkdocs'),'build','--strict','-d',str(out/'site')],
 'structural_quality':[str(bin/'python'),'scripts/check_benchmarks.py','--run-quality'],
}
def run(item):
 name,command=item;log=out/(name+'.log');started=time.perf_counter()
 with log.open('w')as handle:result=subprocess.run(command,cwd=root,env=env,stdout=handle,stderr=subprocess.STDOUT)
 return name,{'command':command,'exit_code':result.returncode,'passed':result.returncode==0,'seconds':time.perf_counter()-started,'log':log.name,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
with ThreadPoolExecutor(max_workers=len(commands))as pool:
 for future in as_completed(pool.submit(run,item)for item in commands.items()):
  name,result=future.result();base['gates'][name]=result
  print(name,result['exit_code'],flush=True)
  (out/'gates.in-progress.json').write_text(json.dumps(base,indent=2)+'\n')
base['source_unchanged_after_checks']=manifest()==rows
base['ending_git_commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
base['git_status_after_checks']=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
base['finished_utc']=datetime.now(timezone.utc).isoformat()
text=(out/'pytest_coverage.log').read_text();match=re.search(r'(\d+) passed(?:, (\d+) skipped)?',text)
if match:base['pytest_summary']={'passed':int(match[1]),'optional_skipped':int(match[2] or 0)}
if(out/'coverage.json').exists():
 cov=json.loads((out/'coverage.json').read_text());base['coverage']={'branch_enabled':cov['meta']['branch_coverage'],'totals':cov['totals'],'report_sha256':hashlib.sha256((out/'coverage.json').read_bytes()).hexdigest()}
base['all_passed']=base['source_unchanged_after_checks']and all(g['passed']for g in base['gates'].values())
(out/'gates.json').write_text(json.dumps(base,indent=2)+'\n')
print(json.dumps({'runtime':rev,'source_tree_sha256':source_hash,'all_passed':base['all_passed'],'pytest':base.get('pytest_summary'),'coverage':base.get('coverage',{}).get('totals',{}).get('percent_covered')},indent=2),flush=True)
raise SystemExit(0 if base['all_passed'] else 1)
