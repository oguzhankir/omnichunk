"""Immutable evidence-container correction. No inference or numeric normalization."""
from __future__ import annotations
import gzip,hashlib,json,os,re,sys
from pathlib import Path
W=Path('/workspace/work/omnichunk-v3');PREV=W/'publication/evidence';OUT=W/'publication-v2/evidence'
sha=lambda b:hashlib.sha256(b).hexdigest()
def write_json(p,x):p.write_text(json.dumps(x,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
def no_vectors(x):
 if isinstance(x,dict):
  for k,v in x.items():
   if k in {'vector','embedding','embeddings'} and isinstance(v,list) and v and (all(type(y) in (int,float) for y in v) or all(isinstance(y,list) and y and all(type(z) in (int,float) for z in y) for y in v)):return False
   if not no_vectors(v):return False
 elif isinstance(x,list):return all(no_vectors(y) for y in x)
 return True
prev_map=PREV/'storage-map-v1.json';prior=json.loads(prev_map.read_text());prev_manifest=json.loads((PREV/'manifest-v1.json').read_text())
OUT.mkdir(parents=True,exist_ok=False)
entries=[];replaced=0;checks=0
for old in prior['entries']:
 row=dict(old);source=Path(row['source_absolute_path']);p=PREV/row['published_relative_path'];stored=p.read_bytes()
 assert sha(stored)==row['stored_sha256'];checks+=1
 current=source.read_bytes();current_sha=sha(current)
 if source==W/'plot_validation.py':
  row['archival_note']='Earlier exact generator snapshot preserved; current finalized generator is top-level/plot_validation_final.py.'
  row['source_current_sha256']=current_sha
 else:assert current_sha==row['source_sha256'],f'Unexpected source change: {source}';checks+=1
 target=OUT/row['published_relative_path'];target.parent.mkdir(parents=True,exist_ok=True);os.link(p,target)
 if row['source_was_gzip']:
  assert current_sha==row['source_sha256'];checks+=1
  assert sha(gzip.decompress(current))==row['raw_sha256'];checks+=1
  if stored!=current:
   target.unlink();target.write_bytes(current);replaced+=1
  row['stored_sha256']=current_sha;row['stored_size_bytes']=len(current)
  row['container_policy']='Exact original compressed source bytes, including original header.'
 entries.append(row)
extra=[(W/'plot_validation_final.py',Path('top-level/plot_validation_final.py'))]
for name in ['plot-audit.json','development-inputs.json','final-report-inputs.json','final-report-number-validation.json','final-table-audit.json','independent-code-agent-narrative-audit.json','validate_final_report_numbers.py','audit_readme_independent_code_agent.py','generate_dev_catalog.py','write_final_report.py','write_readme.py']:
 extra.append((W/'drafts'/name,Path('drafts')/name))
extra.extend([(W/'publication/vector-content-scan.json',Path('publication-audits/vector-content-scan-v1.json')),(Path(__file__),Path('reproduction/build_evidence_v2.py'))])
existing_sources={row['source_absolute_path'] for row in entries};existing_paths={row['published_relative_path'] for row in entries}
for source,relative in extra:
 assert source.is_file(),f'Final supplemental source missing: {source}'
 if str(source) in existing_sources:continue
 raw=source.read_bytes();before=sha(raw);compress=source.suffix in {'.json','.jsonl','.log'};dest=Path(str(relative)+'.gz') if compress else relative
 assert str(dest) not in existing_paths;stored=gzip.compress(raw,mtime=0) if compress else raw
 target=OUT/dest;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(stored)
 assert sha(source.read_bytes())==before,'Supplement changed while staging';checks+=1
 entries.append({'source_absolute_path':str(source),'published_relative_path':dest.as_posix(),'source_sha256':before,'source_size_bytes':len(raw),'raw_sha256':before,'raw_size_bytes':len(raw),'stored_sha256':sha(stored),'stored_size_bytes':len(stored),'encoding':'gzip' if compress else 'identity','source_was_gzip':False})
 existing_sources.add(str(source));existing_paths.add(str(dest))
entries.sort(key=lambda r:r['published_relative_path'])
json_scanned=0
for row in entries:
 p=OUT/row['published_relative_path'];stored=p.read_bytes();assert sha(stored)==row['stored_sha256'];checks+=1
 assert len(stored)==row['stored_size_bytes'];checks+=1
 raw=gzip.decompress(stored) if row['encoding']=='gzip' else stored
 assert sha(raw)==row['raw_sha256'];checks+=1
 assert len(raw)==row['raw_size_bytes'];checks+=1
 if row['source_was_gzip']:assert sha(stored)==row['source_sha256'];checks+=1
 if p.name.endswith('.json.gz'):
  assert no_vectors(json.loads(raw)),f'Numeric vector array in {p}';checks+=1;json_scanned+=1
 assert p.suffix.lower() not in {'.npy','.npz','.safetensors','.bin','.pt','.pth','.parquet','.arrow','.fernet','.enc','.key','.pyc','.pyo','.lock','.zip'};checks+=1
 if p.suffix!='.bundle':assert not re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----',raw);checks+=1
 # Prove no byte was changed through hardlinks in the earlier immutable archive.
 if row['source_absolute_path'] in {x['source_absolute_path'] for x in prior['entries']}:
  old=next(x for x in prior['entries'] if x['source_absolute_path']==row['source_absolute_path'])
  assert sha((PREV/old['published_relative_path']).read_bytes())==old['stored_sha256'];checks+=1
storage={'schema_version':1,'version':2,'supersedes_container_layout_only':'v1 raw artifact payloads remain unchanged; original existing gzip bytes now match source container hashes exactly. v1 staging remains intact.','prior_storage_map_sha256':sha(prev_map.read_bytes()),'scope':'Already-compressed sources are archived byte-for-byte; only plain JSON/log source bytes use deterministic mtime=0 gzip. No numeric or source-code content normalization.','entries':entries}
write_json(OUT/'storage-map-v2.json',storage)
manifest={'schema_version':1,'version':2,'storage_map':'storage-map-v2.json','storage_map_sha256':sha((OUT/'storage-map-v2.json').read_bytes()),'artifact_files':len(entries),'raw_bytes':sum(x['raw_size_bytes'] for x in entries),'stored_bytes':sum(x['stored_size_bytes'] for x in entries),'existing_gzip_artifacts':sum(x['source_was_gzip'] for x in entries),'restored_original_containers':replaced,'files':{x['published_relative_path']:x['stored_sha256'] for x in entries},'excluded_files':prev_manifest['excluded_files'],'excluded_unscanned_roots':prev_manifest['excluded_unscanned_roots'],'unit_only_scripts':prev_manifest['unit_only_scripts']}
write_json(OUT/'manifest-v2.json',manifest)
verification={'status':'passed','version':2,'checks':checks,'artifact_files':len(entries),'new_artifact_files':len(entries)-len(prior['entries']),'stored_bytes':manifest['stored_bytes'],'raw_bytes':manifest['raw_bytes'],'restored_original_gzip_containers':replaced,'existing_gzip_artifacts':manifest['existing_gzip_artifacts'],'json_artifacts_scanned_for_vectors':json_scanned,'storage_map':'storage-map-v2.json','storage_map_sha256':manifest['storage_map_sha256'],'manifest':'manifest-v2.json','manifest_sha256':sha((OUT/'manifest-v2.json').read_bytes()),'max_stored_file_bytes':max(x['stored_size_bytes'] for x in entries),'scope':'All stored/source-container/raw hashes and lengths; gzip roundtrips; numeric-vector and private-key/type bans; v1 archive integrity rechecked.'}
write_json(OUT/'verification-v2.json',verification);write_json(W/'publication-v2/latest-result.json',verification)
print(json.dumps(verification,indent=2))
