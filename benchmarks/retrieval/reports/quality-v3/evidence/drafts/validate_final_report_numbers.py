"""Tie displayed numeric tokens to hashed raw JSON values or explicit derivations.

This complements the semantic table audit; numeric matching alone does not
establish correct scientific interpretation. Code identifiers, hashes and URLs
are metadata, not measured numeric claims.
"""
from __future__ import annotations
from pathlib import Path
import collections,gzip,hashlib,json,re,math,datetime
W=Path('/workspace/work/omnichunk-v3');D=W/'drafts';report=D/'README-final.md'
sha=lambda b:hashlib.sha256(b).hexdigest()
ledger=json.loads((D/'final-report-inputs.json').read_text());dev=json.loads((D/'development-inputs.json').read_text())
source_specs={str(W/k):(k,v['sha256']) for k,v in ledger['all_source_inputs'].items() if k.endswith(('.json','.json.gz'))}
for a in dev['artifacts']:
 if a['absolute_input'].endswith(('.json','.json.gz')):source_specs[a['absolute_input']]=(a['path'],a['sha256'])
# Additional policy/count records used in the prose.
for p in [W/'protocol.json',W/'belebele_protocol.json',W/'code-files/protocol.json',W/'parent-retrieval/validation/rival-comparisons.json',W/'parent-retrieval/validation/row-hashes.json.gz',W/'parent-retrieval/validation/identity-cache-audit.json']:
 if p.exists():source_specs[str(p)]=(str(p.relative_to(W)),sha(p.read_bytes()))
index=collections.defaultdict(list);sources={};numeric_source_values=0
number_re=re.compile(r'(?<![A-Za-z0-9_.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:e[-+]?\d+)?%?(?![A-Za-z0-9_.])',re.I)
def register(display,source):
 index[display].append(source)
def record_numeric(value,source):
 global numeric_source_values
 if isinstance(value,bool) or not math.isfinite(float(value)):return
 numeric_source_values+=1
 reps={str(value),format(float(value),'.6f'),format(float(value),'.2f'),format(float(value),'.0f') if float(value).is_integer() else str(value)}
 for k in reps:register(k,{**source,'raw_value':value,'kind':'raw-numeric-value'})
def walk(value,path,source):
 if isinstance(value,(int,float)) and not isinstance(value,bool):record_numeric(value,{**source,'json_pointer':path})
 elif isinstance(value,list):
  for i,v in enumerate(value):walk(v,path+'/'+str(i),source)
 elif isinstance(value,dict):
  for k,v in value.items():
   if k in ['per_query','passages','per_query_results','runtime_files','harness_files','model_files','license_records','corpus_provenance','records','rows','query_seconds_samples','chunk_seconds_samples']:continue
   walk(v,path+'/'+str(k).replace('~','~0').replace('/','~1'),source)
 elif isinstance(value,str) and len(value)<3000 and not re.fullmatch('[0-9a-f]{40,64}',value):
  # Predeclared numeric policy values can be embedded in interpretation strings.
  for m in number_re.finditer(value):
   token=m.group().rstrip('%').replace(',','').lstrip('+')
   register(token,{**source,'json_pointer':path,'kind':'declared-policy-string','raw_string':value,'matched_substring':m.group()})
for absolute,(relative,expected) in source_specs.items():
 p=Path(absolute);raw=p.read_bytes();assert sha(raw)==expected,p
 try:x=json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
 except (ValueError,UnicodeError):continue
 sources[relative]={'sha256':expected,'bytes':len(raw)};walk(x,'',{'artifact':relative,'artifact_sha256':expected})
# Explicit, auditable arithmetic used in inline claims and inventory counts.
derived=[]
def derive(name,value,expression,inputs):
 d={'name':name,'value':value,'expression':expression,'inputs':inputs};derived.append(d)
 for k in {str(value),format(float(value),'.6f'),format(float(value),'.2f')}:
  register(k,{'kind':'derived','derivation':name,'raw_value':value})
def source_value(path,tool,cap,key):
 raw=Path(path).read_bytes();x=json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)
 for i,c in enumerate(x['candidates']):
  if c['tool']==tool and c['chunk_capacity']==cap:return {'artifact':str(Path(path).relative_to(W)),'artifact_sha256':sha(raw),'json_pointer':f'/candidates/{i}/{key}','value':c[key]}
 raise ValueError((path,tool,cap))
a=source_value(W/'validation/code/english/candidate-final-d0/report.json.gz','omnichunk-code-compact',64,'chunks');b=source_value(W/'validation/code/english/baseline/report.json.gz','semchunk',64,'chunks')
derive('English64 vector reduction percentage versus semchunk',100*(1-a['value']/b['value']),'100 * (1 - candidate_vectors / reference_vectors)',[a,b])
summary=json.loads((W/'validation/candidate-results-summary.json').read_text())
base_counts=[len(case['successful_baselines_512']) for case in summary['cases']]
derive('Successful primary baseline cells',sum(base_counts),'sum(successful_baselines_512 lengths over five cases)',[{'artifact':'validation/candidate-results-summary.json','artifact_sha256':sha((W/'validation/candidate-results-summary.json').read_bytes()),'json_pointer':f'/cases/{i}/successful_baselines_512','length':c} for i,c in enumerate(base_counts)])
derive('Baseline declared cells',100,'5 views/models * 10 strategies * 2 capacities',[{'artifact':'freeze-before-validation-v3.json','artifact_sha256':sha((W/'freeze-before-validation-v3.json').read_bytes()),'policy':'five frozen view/model cases; ten declared strategy types; capacities64/96'}])
derive('Failed baseline cells',100-sum(base_counts),'declared100 - successful95',[{'derivations':['Baseline declared cells','Successful primary baseline cells']}])
derive('Final candidate primary cells',sum(len(c['primary_512']) for c in summary['cases']),'sum(primary_512 lengths over cases)',[{'artifact':'validation/candidate-results-summary.json','artifact_sha256':sha((W/'validation/candidate-results-summary.json').read_bytes()),'json_pointer':'/cases'}])
p=W/'code-files/protocol.json';obj=json.loads(p.read_text());assert '30000' in obj['eligibility']
register('30000',{'kind':'declared-policy-string','artifact':'code-files/protocol.json','artifact_sha256':sha(p.read_bytes()),'json_pointer':'/eligibility','raw_string':obj['eligibility'],'matched_substring':'30000'})
p=W/'dataset-readme-reproduction-audit.json';obj=json.loads(p.read_text());derive('Source and attribution byte checks across six rebuilt splits',sum(r['source_and_attribution_byte_checks'] for r in obj['rebuilds']),'sum(rebuilds[*].source_and_attribution_byte_checks)',[{'artifact':'dataset-readme-reproduction-audit.json','artifact_sha256':sha(p.read_bytes()),'json_pointer':f'/rebuilds/{i}/source_and_attribution_byte_checks','value':r['source_and_attribution_byte_checks']} for i,r in enumerate(obj['rebuilds'])])
p=W/'parent-retrieval/validation/paired.json';obj=json.loads(p.read_text());assert 'seed20261027' in obj['bootstrap']
register('20261027',{'kind':'declared-policy-string','artifact':'parent-retrieval/validation/paired.json','artifact_sha256':sha(p.read_bytes()),'json_pointer':'/bootstrap','raw_string':obj['bootstrap'],'matched_substring':'seed20261027'})
# Per-source intervals, counts and policy values matching each displayed token.
claims=[];unmatched=[]
for lineno,line in enumerate(report.read_text().splitlines(),1):
 clean=re.sub(r'`[^`]*`','',line);clean=re.sub(r'https?://\S+','',clean);clean=re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z)','',clean)
 # Python/semantic-version identifiers are provenance strings, not partial decimals.
 clean=re.sub(r'(?<!\d)\d+\.\d+\.\d+(?!\d)','',clean)
 for m in number_re.finditer(clean):
  raw=m.group();token=raw.rstrip('%').replace(',','').lstrip('+');negative=token.startswith('-')
  candidates=index.get(token,[])
  if not candidates:
   try:
    z=float(token);keys={str(int(z)) if z.is_integer() else str(z),format(z,'.6f'),format(z,'.2f')};candidates=[v for k in keys for v in index.get(k,[]) if v.get('kind')=='raw-numeric-value' and abs(float(v['raw_value'])-z)<=max(0.5*10**(-len(token.split('.')[1])) if '.' in token else 0,1e-15)]
   except ValueError:candidates=[]
  # Prefer exact case/raw statistic paths, retaining alternatives for independent review.
  context=re.match(r'\| (turkish|code|code-files) / (ML|EN) / (64|96)',line)
  if context:
   domain,model,cap=context.groups();model='multilingual' if model=='ML' else 'english';prefixes=[f'validation/{domain}/'+(model+'/' if domain!='turkish' else ''),f'comparisons/validation/{domain}/'+(model+'/' if domain!='turkish' else '')]
  else:prefixes=[]
  def rank(v):
   artifact=v.get('artifact','');pointer=v.get('json_pointer','')
   return (0 if any(artifact.startswith(p) for p in prefixes) else 1,0 if v.get('kind') in ['raw-numeric-value','derived'] else 1,0 if '/all/' in pointer or '/coverage/' in pointer else 1,artifact,pointer)
  chosen=sorted(candidates,key=rank)[:5]
  entry={'line':lineno,'text':line,'display':raw,'normalized_numeric':token,'location':'table-cell' if line.startswith('|') else 'inline','matching_source_count':len(candidates),'sources':chosen}
  claims.append(entry)
  if not chosen:unmatched.append(entry)
result={'schema_version':1,'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'report_sha256':sha(report.read_bytes()),'scope':'Every displayed numeric token outside code identifiers, hashes, URLs, timestamps and semantic-version identifiers; complements independent semantic table audit','claim_count':len(claims),'matched_claims':len(claims)-len(unmatched),'unmatched_claims':unmatched,'source_numeric_values':numeric_source_values,'sources':sources,'derivations':derived,'claims':claims,'limitations':'Numeric source matching verifies exact/rounded values and declared policies; semantic attribution and scientific interpretation additionally require the independent table/narrative review.'}
semantic_path=D/'final-table-audit.json'
if semantic_path.exists():
 semantic=json.loads(semantic_path.read_text())
 assert semantic['readme_sha256']==sha(report.read_bytes()) and semantic['all_table_checks_passed'] and not semantic['errors']
 result['independent_semantic_table_audit']={'path':'final-table-audit.json','sha256':sha(semantic_path.read_bytes()),'report_sha256':semantic['readme_sha256'],'numeric_table_checks':semantic['table_numeric_checks'],'frozen_reference_identities':semantic['frozen_reference_identities_checked'],'extra_inline_real_file_96_checks':len(semantic['inline_real_file_96_own_baseline_checks']),'all_passed':True}
(D/'final-report-number-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'claims':len(claims),'matched':len(claims)-len(unmatched),'unmatched':[{'line':c['line'],'display':c['display'],'text':c['text'][:160]} for c in unmatched],'manifest_sha256':sha((D/'final-report-number-validation.json').read_bytes())}))
