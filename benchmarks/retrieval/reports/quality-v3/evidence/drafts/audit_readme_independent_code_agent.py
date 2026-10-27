from pathlib import Path
import json,gzip,re,hashlib
P=Path('/workspace/work/omnichunk-v3');D=(P/'drafts/README-final.md').read_text();errors=[];checks=0;ledger={};checkdetails=[];cell_sources=[];active_paths=set()

def ck(ok,msg):
 global checks
 checks+=1
 checkdetails.append({'passed':bool(ok),'claim':msg,'source_paths':sorted(active_paths)})
 if not ok:errors.append(msg)
def eq(x,y,msg):ck(abs(float(x)-float(y))<=0.00000051,msg+f': {x} != {y}')
def loc(view,model):return P/'validation'/view/(model if view!='turkish' else '')
def report(path):
 ledger[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();active_paths.add(str(path));return json.loads(gzip.decompress(path.read_bytes()))
cache={}
def base(view,model):
 key=(view,model)
 if key not in cache:
  vals={}
  for p in loc(*key).glob('baseline*/report.json.gz'):
   j=report(p)
   for c in j['candidates']:
    if c['status']=='ok':
     c['_audit_sourcepath']=str(p);vals[(c['tool'],c['chunk_capacity'])]=c
  cache[key]=vals
 return cache[key]
def cand(view,model,profile,cap):
 j=report(loc(view,model)/'candidate-final-d0/report.json.gz');tool='omnichunk'+('' if profile=='default' else '-'+profile)
 return next(c for c in j['candidates'] if c['tool']==tool and c['chunk_capacity']==cap),j

def pair(view,model,profile,ref,cap):
 folder=P/'comparisons/validation'/view/(model if view!='turkish' else '')/'512'/('omnichunk'+('' if profile=='default' else '-'+profile))
 paths=[folder/f'vs-{ref}.json',folder/f'vs-{ref}-96-only.json']
 for p in paths:
  if p.exists():
   ledger[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();active_paths.add(str(p));j=json.loads(p.read_text())
   for c in j['comparisons']:
    if c['chunk_capacity']==cap:return c['slices']['all']['metrics']['recall']
 raise KeyError((view,model,profile,ref,cap))
def parsekey(k):
 v,m,c=k.split(' / ');return v,{'ML':'multilingual','EN':'english'}[m],int(c)
countcost=countprimary=countcontrol=countdefault=0
for line in D.splitlines():
 if not re.match(r'\| (turkish|code|code-files) / ',line):continue
 f=[x.strip() for x in line.strip('|').split('|')]
 if len(f[0].split(' / '))!=3:continue
 active_paths.clear();v,m,cap=parsekey(f[0]);b=base(v,m);active_paths.update(c['_audit_sourcepath'] for c in b.values())
 if len(f)==7 and re.fullmatch(r'[0-9.]+',f[3]):
  c,j=cand(v,m,f[1],cap);met=c['summary']['all']['evidence_at_budget']
  for key,s in zip(['recall','precision','iou'],f[2:5]):eq(s,met[key],line)
  eq(f[5],c['chunks'],line);w=next(x for x in j['configuration']['dense_embeddings']['producer_metadata']['candidate_workloads'] if x['tool']==c['tool'] and x['chunk_capacity']==cap);eq(f[6],w['passage_input_tokens'],line);countcost+=1
 elif len(f)==7:
  profile='prose-compact' if v=='turkish' else 'code-compact';c,j=cand(v,m,profile,cap);eq(f[2],c['summary']['all']['evidence_at_budget']['recall'],line);ref=f[3];eq(f[4],b[(ref,cap)]['summary']['all']['evidence_at_budget']['recall'],line);p=pair(v,m,profile,ref,cap)
  nums=re.findall(r'[+-]?\d+\.\d+',f[5]);eq(nums[0],p['mean_delta'],line)
  for s,x in zip(nums[1:],p['bootstrap_delta_ci_95']):eq(s,x,line)
  ck(f[6]==f"{p['wins']}/{p['ties']}/{p['losses']}",line);countprimary+=1
 elif len(f)==6:
  profile='prose-compact' if v=='turkish' else 'code-compact';c,j=cand(v,m,profile,cap);eq(f[1],b[('fixed',cap)]['summary']['all']['evidence_at_budget']['recall'],line)
  for ref,cell in [('fixed',f[2]),(f[3].split(':')[0],f[4])]:
   p=pair(v,m,profile,ref,cap);ns=re.findall(r'[+-]?\d+\.\d+',cell)
   for s,x in zip(ns,[p['mean_delta']]+p['bootstrap_delta_ci_95']):eq(s,x,line)
  ref,mean=f[3].split(': ');eq(mean,b[(ref,cap)]['summary']['all']['evidence_at_budget']['recall'],line)
  best=max(x['summary']['all']['evidence_at_budget']['recall'] for (t,capx),x in b.items() if t not in ['omnichunk','fixed'] and capx==cap);eq(mean,best,line)
  ns=[int(x.strip()) for x in f[5].split('/')];ck(ns==[c['chunks'],b[('fixed',cap)]['chunks'],b[(ref,cap)]['chunks']],line);countcontrol+=1
 elif len(f)==5:
  c,j=cand(v,m,'default',cap);p=pair(v,m,'default','omnichunk',cap);ns=re.findall(r'[+-]?\d+\.\d+',f[1]);eq(ns[0],p['baseline_mean'],line);eq(ns[1],p['candidate_mean'],line);ns=re.findall(r'[+-]?\d+\.\d+',f[2]);
  for s,x in zip(ns,[p['mean_delta']]+p['bootstrap_delta_ci_95']):eq(s,x,line)
  countdefault+=1
ck(countcost==30,'30costrows');ck(countprimary==10,'10primaryrows');ck(countcontrol==10,'10controlrows');ck(countdefault==10,'10defaultrows')
print(json.dumps({'checks':checks,'errors':errors,'costrows':countcost,'primaryrows':countprimary,'controlrows':countcontrol,'defaultrows':countdefault},indent=2));(P/'drafts/independent-code-agent-narrative-audit.json').write_text(json.dumps({'checks':checks,'errors':errors,'sha256':hashlib.sha256(D.encode()).hexdigest()},indent=2)+'\n')

choices_path=P/'reference-choices-before-validation.json'
choices=json.loads(choices_path.read_text());ledger[str(choices_path)]=hashlib.sha256(choices_path.read_bytes()).hexdigest()
primary_rows={}
for l in D.splitlines():
 if not re.match(r'\| (turkish|code|code-files) / ',l):continue
 fs=[z.strip() for z in l.strip('|').split('|')]
 if len(fs)==7 and not re.fullmatch(r'[0-9.]+',fs[3]):
  primary_rows[parsekey(fs[0])]=fs
for x in choices['choices']:
 fs=primary_rows[(x['domain'],x['model'],x['chunk_capacity'])]
 assert fs[1]==x['candidate_profile'].removeprefix('omnichunk-') and fs[3]==x['named_reference']
result={'schema_version':1,'scope':'Independent raw-source check of all60primary512table rows (30profilecost+10preselected+10fixedobservedcontrols+10defaultprior), plus all10frozen reference/profile identities. No inference, ranking, data, runtime or parameter changes.','readme_path':str(P/'drafts/README-final.md'),'readme_sha256':hashlib.sha256(D.encode()).hexdigest(),'table_numeric_checks':checks,'all_table_checks_passed':not errors,'errors':errors,'table_rows':{'profile_quality_cost':countcost,'preselected_primary':countprimary,'fixed_and_observed_named':countcontrol,'default_vs_prior':countdefault},'frozen_reference_identities_checked':len(choices['choices']),'source_file_hashes':ledger,'audit_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'checks':checkdetails,'qualitative_review':['Fixed exact EN64recall/precision/IoUties confirmed;named positiveinterval unadjusted and scoped','Custody loss and exacthash reconstruction disclosed accurately','Wholefunction/wholepassage proxygold limits clear','Codefileviewcorrelatednotindependent','No Pareto/general superiority inferred fromcost reductions','Parent/windowstudy sentence explicitly scopequalified;no contradiction with primarynamed positiveCI']}
(P/'drafts/final-table-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'saved':str(P/'drafts/final-table-audit.json'),'checks':checks,'errors':errors,'reference_identities':len(choices['choices']),'rawfiles':len(ledger),'readme_sha256':result['readme_sha256']}))
