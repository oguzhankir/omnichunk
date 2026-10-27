"""Select references solely from frozen development results, never validation."""
import gzip
import hashlib
import json
from pathlib import Path

W=Path(__file__).resolve().parent
def read(p):
 raw=p.read_bytes();return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
def path(directory):
 for n in ['report.json.gz','report.json']:
  p=directory/n
  if p.exists():return p
 raise FileNotFoundError(directory)
choices=[]
for domain,models in [('turkish',['multilingual']),('code',['multilingual','english']),('code-files',['multilingual','english'])]:
 for model in models:
  base=W/'dev'/domain
  if domain!='turkish':base/=model
  dirs=([base/'baseline',base/'semantic-code'] if domain=='turkish' else [base/'baseline-summary',base/'semantic-code'] if domain=='code' else [base/'baseline']+([base/'chonkie-sentence-96',base/'chonkie-sentence-64-failed'] if model=='english' else []))
  rows=[];inputs={}
  for directory in dirs:
   p=path(directory);d=read(p);inputs[str(p.relative_to(W))]=hashlib.sha256(p.read_bytes()).hexdigest()
   if d['configuration']['retrieval_budget']!=512:raise ValueError('Selection uses primary budget only')
   rows.extend(d['candidates'])
  for cap in [64,96]:
   valid=[r for r in rows if r['chunk_capacity']==cap and r['status']=='ok' and r['tool'] not in ['omnichunk','fixed']]
   def key(r):
    e=r['summary']['all']['evidence_at_budget'];return (-e['recall'],-e['precision'],r['chunks'],r['tool'])
   winner=sorted(valid,key=key)[0]
   choices.append({'domain':domain,'model':model,'chunk_capacity':cap,'candidate_profile':'omnichunk-prose-compact' if domain=='turkish' else 'omnichunk-code-compact','named_reference':winner['tool'],'development_evidence':winner['summary']['all']['evidence_at_budget'],'development_vectors':winner['chunks'],'fixed_control_always_reported':True,'inputs':inputs})
out=W/'reference-choices-before-validation.json'
if out.exists():raise ValueError('Never replace a declared selection')
out.write_text(json.dumps({'rule':'highest development primary recall, then precision, fewer vectors, stable tool name; no validation input','choices':choices},indent=2)+'\n')
print(json.dumps([{'domain':c['domain'],'model':c['model'],'capacity':c['chunk_capacity'],'reference':c['named_reference']} for c in choices]))
