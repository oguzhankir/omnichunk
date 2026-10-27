"""Stage exact experimental evidence; no model inference or repository edits."""
from __future__ import annotations
import argparse,gzip,hashlib,json,re,sys
from pathlib import Path
W=Path('/workspace/work/omnichunk-v3');H=W/'frozen-candidate-v3';OUT=W/'publication/evidence'
DIRS=['dev','validation','frontier','comparisons','adapter-audit','context-dense-development','parent-retrieval','environment','proof-v2','proof-v3','final-gates-c1','final-gates-d0','drafts/external-quality-screen']
EXCLUDED_PARTS={'.git','__pycache__','.pytest_cache','.hypothesis','.ruff_cache','nltk_data','site','.venv','venv','node_modules'}
BANNED_SUFFIX={'.npy','.npz','.safetensors','.bin','.pt','.pth','.parquet','.arrow','.fernet','.enc','.key','.pyc','.pyo','.lock','.zip'}
ALLOWED={'.json','.jsonl','.log','.txt','.py','.md','.csv','.svg','.bundle','.yml','.yaml','.toml'}
ROOT_EXCLUDE={'root-state.json'}
ROOT_TEXT={'.json','.jsonl','.log','.txt','.py','.md','.csv','.svg','.bundle'}

def sha(b):return hashlib.sha256(b).hexdigest()
def write_json(p,v):p.write_text(json.dumps(v,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
def effective_suffix(p):return Path(p.stem).suffix.lower() if p.suffix.lower()=='.gz' else p.suffix.lower()
def reject(p,relative):
 if any(part in EXCLUDED_PARTS for part in relative.parts):return 'cache/generated-site/dependency asset'
 if p.name in ROOT_EXCLUDE:return 'internal agent planning/state'
 if p.suffix.lower() in BANNED_SUFFIX:return 'banned binary/weight/vector/ciphertext/dependency asset'
 low=p.name.lower()
 if 'vectors' in low and effective_suffix(p) in {'.json','.jsonl'}:return 'actual or temporary embedding-vector artifact'
 if 'decoded' in low and 'vector' in low:return 'decoded vector temporary'
 if effective_suffix(p) not in ALLOWED:return 'not an explicit evidence text/source/archive type'
 if 'private-key' in low or low.endswith('.pem'):return 'private key material'
 return None

def select():
 selected=[];excluded=[]
 for name in DIRS:
  base=W/name
  if not base.exists():continue
  for p in sorted(base.rglob('*')):
   if not p.is_file():continue
   rel=p.relative_to(W);reason=reject(p,rel)
   if reason:excluded.append({'source_absolute_path':str(p),'reason':reason})
   else:selected.append((p,rel))
 for p in sorted(W.iterdir()):
  if p.is_file() and p.suffix.lower() in ROOT_TEXT:
   reason=reject(p,p.relative_to(W))
   if reason:excluded.append({'source_absolute_path':str(p),'reason':reason})
   else:selected.append((p,Path('top-level')/p.name))
 # Exact helper sources are archived independently of their worktrees.
 for name in ['benchmarks/run_retrieval.py','benchmarks/prepare_dense.py','benchmarks/compare_retrieval.py','benchmarks/run_dense_experiment.py','benchmarks/retrieval/requirements.txt']:
  p=H/name;selected.append((p,Path('frozen-harness')/name))
 for p in sorted((H/'benchmarks/retrieval').glob('*.py')):selected.append((p,Path('frozen-harness')/p.relative_to(H)))
 for name in ['matrix.py','screen.py','frontier.py']:
  p=Path('/workspace/work/omnichunk-quality')/name
  if p.is_file():selected.append((p,Path('reproduction/external-quality-helpers')/name))
 for name in ['external-screen-storage-map.json']:
  p=W/'drafts'/name
  if p.is_file():selected.append((p,Path('external-screen-provenance')/name))
 selected.append((Path(__file__),Path('reproduction/build_evidence.py')))
 # Unit scripts are code, never quality-data artifacts.
 selected=[(p,Path('unit-test-scripts')/rel.name if p.name.startswith('test_') else rel) for p,rel in selected]
 result={}
 for p,rel in selected:
  if str(p) in result and result[str(p)]!=rel:raise ValueError('Ambiguous source mapping')
  result[str(p)]=rel
 return [(Path(p),rel) for p,rel in sorted(result.items())],excluded

def embedded_vectors(value):
 if isinstance(value,dict):
  for key,child in value.items():
   if key in {'vector','embedding'} and isinstance(child,list) and len(child)>=8 and all(isinstance(x,(int,float)) for x in child):return True
   if embedded_vectors(child):return True
 elif isinstance(value,list):
  return any(embedded_vectors(x) for x in value)
 return False

def build(append=False):
 OUT.mkdir(exist_ok=append,parents=True)
 version=1
 while (OUT/f'storage-map-v{version}.json').exists():version+=1
 prior=[]
 if version>1:
  if not append:raise ValueError('Existing evidence; use append without modifying old artifacts')
  prior=json.loads((OUT/f'storage-map-v{version-1}.json').read_text())['entries']
 by_source={x['source_absolute_path']:x for x in prior};by_dest={x['published_relative_path']:x for x in prior}
 selected,excluded=select();added=0
 for source,relative in selected:
  source_bytes=source.read_bytes();source_hash=sha(source_bytes)
  if str(source) in by_source:
   old=by_source[str(source)]
   if old['source_sha256']!=source_hash:raise ValueError(f'Already staged source changed; preserve/resolve explicitly: {source}')
   continue
  zipped=source.suffix.lower()=='.gz';raw=gzip.decompress(source_bytes) if zipped else source_bytes
  suffix=effective_suffix(source);compress=suffix in {'.json','.jsonl','.log'}
  if suffix=='.json':
   parsed=json.loads(raw)
   if embedded_vectors(parsed):raise ValueError(f'Actual embedding vectors in non-vector artifact: {source}')
  if suffix!='.bundle' and re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',raw):raise ValueError(f'Private key content: {source}')
  if suffix!='.bundle' and re.search(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{40,})',raw):raise ValueError(f'Credential-shaped content requires review: {source}')
  if compress:
   dest=relative if zipped else Path(str(relative)+'.gz')
   stored=gzip.compress(raw,mtime=0)
  else:dest=relative;stored=source_bytes
  if str(dest) in by_dest:raise ValueError(f'Destination collision: {dest}')
  target=OUT/dest;target.parent.mkdir(parents=True,exist_ok=True)
  if target.exists():raise ValueError(f'Never overwrite staged artifact: {target}')
  target.write_bytes(stored)
  if sha(source.read_bytes())!=source_hash:raise ValueError(f'Input changed while staging: {source}')
  row={'source_absolute_path':str(source),'published_relative_path':dest.as_posix(),'source_sha256':source_hash,'source_size_bytes':len(source_bytes),'raw_sha256':sha(raw),'raw_size_bytes':len(raw),'stored_sha256':sha(stored),'stored_size_bytes':len(stored),'encoding':'gzip' if compress else 'identity','source_was_gzip':zipped}
  by_source[str(source)]=row;by_dest[str(dest)]=row;added+=1
 entries=sorted(by_source.values(),key=lambda x:x['published_relative_path'])
 checks=0
 for row in entries:
  p=OUT/row['published_relative_path'];stored=p.read_bytes();assert sha(stored)==row['stored_sha256'];checks+=1
  raw=gzip.decompress(stored) if row['encoding']=='gzip' else stored
  assert sha(raw)==row['raw_sha256'];checks+=1
  assert len(raw)==row['raw_size_bytes'];checks+=1
  assert not reject(p,Path(row['published_relative_path']));checks+=1
 storage={'schema_version':1,'version':version,'scope':'Exact-byte evidence archive; source paths record original workspace locations. JSON/logs use deterministic mtime=0 gzip; raw payload and stored/source file hashes remain explicit. Unit scripts are not quality data. No vectors, weights, datasets cache, worktrees or private custody material included.','entries':entries}
 storage_name=f'storage-map-v{version}.json';write_json(OUT/storage_name,storage)
 manifest={'schema_version':1,'storage_map':storage_name,'storage_map_sha256':sha((OUT/storage_name).read_bytes()),'artifact_files':len(entries),'new_artifact_files':added,'raw_bytes':sum(x['raw_size_bytes'] for x in entries),'stored_bytes':sum(x['stored_size_bytes'] for x in entries),'files':{x['published_relative_path']:x['stored_sha256'] for x in entries},'excluded_files':excluded,'excluded_unscanned_roots':['all worktrees (including final-gates-8d)','upstream','code data/import caches','code-files data/import caches','turkish data/import caches','extension-smoke','extension-smoke-final','dataset-readme-reproduction','public-stage','encoder-slots','root-state.json'],'unit_only_scripts':[x['published_relative_path'] for x in entries if x['published_relative_path'].startswith('unit-test-scripts/')]}
 manifest_name=f'manifest-v{version}.json';write_json(OUT/manifest_name,manifest)
 verification={'status':'passed','version':version,'checks':checks,'artifact_files':len(entries),'new_artifact_files':added,'stored_bytes':manifest['stored_bytes'],'raw_bytes':manifest['raw_bytes'],'storage_map':storage_name,'storage_map_sha256':manifest['storage_map_sha256'],'manifest':manifest_name,'manifest_sha256':sha((OUT/manifest_name).read_bytes()),'max_stored_file_bytes':max(x['stored_size_bytes'] for x in entries),'scope':'Every staged artifact stored SHA/raw SHA/length and gzip roundtrip, explicit type bans, JSON actual-vector scan, private-key/credential-shaped-content scan. Does not attest model training/data suitability.'}
 write_json(OUT/f'verification-v{version}.json',verification)
 write_json(W/'publication/latest-result.json',verification)
 print(json.dumps(verification,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--append',action='store_true');a=p.parse_args();build(a.append)
