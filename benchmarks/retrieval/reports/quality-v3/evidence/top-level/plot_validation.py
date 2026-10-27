"""Plot frozen primary-reference differences and complete quality/workload points."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

W=Path(__file__).resolve().parent
OUT=W/'drafts';OUT.mkdir(exist_ok=True)
S=json.loads((W/'validation/candidate-results-summary.json').read_text())
CHOICES=json.loads((W/'reference-choices-before-validation.json').read_text())['choices']
LOOKUP={(c['domain'],c['model']):c for c in S['cases']}
LABELS={('turkish','multilingual'):'Turkish passages / multilingual',('code','multilingual'):'Python functions / multilingual',('code','english'):'Python functions / English',('code-files','multilingual'):'Original Python files / multilingual',('code-files','english'):'Original Python files / English'}
ORDER=list(LABELS)
NAMES={'semantic-code':'ST code','semantic-text-splitter':'ST text','llamaindex-sentence':'LlamaIndex sentence','chonkie-sentence':'Chonkie sentence','semchunk':'semchunk','langchain':'LangChain'}
COLORS={'omnichunk':'#2166ac','omnichunk-prose-compact':'#e08214','omnichunk-code-compact':'#1b9e77'}
plt.rcParams.update({'font.size':9,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})

rows=[]
for domain,model in ORDER:
 case=LOOKUP[(domain,model)]
 for cap in [64,96]:
  choice=next(c for c in CHOICES if (c['domain'],c['model'],c['chunk_capacity'])==(domain,model,cap))
  point=next(c for c in case['primary_512'] if c['tool']==choice['candidate_profile'] and c['capacity']==cap)
  ref=next(c for c in case['successful_baselines_512'] if c['tool']==choice['named_reference'] and c['capacity']==cap)
  metric=point['paired_metrics_512'][ref['tool']]['recall']
  lo,hi=metric['bootstrap_delta_ci_95']
  rows.append({'domain':domain,'model':model,'capacity':cap,'profile':point['tool'],'reference':ref['tool'],'recall':point['evidence_at_budget']['recall'],'reference_recall':ref['recall'],'delta':metric['mean_delta'],'ci_low':lo,'ci_high':hi,'vectors':point['chunks'],'reference_vectors':ref['chunks'],'vector_ratio':point['chunks']/ref['chunks']})
with (OUT/'primary-reference-points.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
fig,(ax,bx)=plt.subplots(1,2,figsize=(13,7.2),gridspec_kw={'width_ratios':[2.3,1]},sharey=True)
ys=list(range(len(rows)))
for y,r in zip(ys,rows):
 color='#18784a' if r['ci_low']>0 else '#b2182b' if r['ci_high']<0 else '#586875'
 ax.errorbar(r['delta']*100,y,xerr=[[(r['delta']-r['ci_low'])*100],[(r['ci_high']-r['delta'])*100]],fmt='o',color=color,capsize=3,markersize=5)
 bx.plot(r['vector_ratio'],y,'o',color=COLORS[r['profile']],markersize=5)
 bx.annotate(f" {r['vectors']}/{r['reference_vectors']}",(r['vector_ratio'],y),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
ax.set_yticks(ys,[f"{LABELS[(r['domain'],r['model'])]} | {r['capacity']}" for r in rows]);ax.invert_yaxis()
ax.axvline(0,color='#333333',lw=1);bx.axvline(1,color='#333333',lw=1)
ax.set_xlabel('Recall difference (percentage points)');bx.set_xlabel('Index vector ratio\ncandidate / frozen named reference')
bx.set_xlim(min(r['vector_ratio'] for r in rows)-.06,max(1.15,max(r['vector_ratio'] for r in rows)+.24))
ax.grid(axis='x',alpha=.2);bx.grid(axis='x',alpha=.2)
for y in [1.5,3.5,5.5,7.5]:ax.axhline(y,color='#dddddd',lw=.6);bx.axhline(y,color='#dddddd',lw=.6)
fig.suptitle('Held-out primary profiles versus development-selected named references\n512 native-token context; child capacities 64 and 96',fontsize=12)
fig.text(.01,.015,'All profiles/references were frozen before validation. Intervals: unadjusted 95% clustered bootstrap; correlated models/views are not independent.\nGreen/red indicate an interval above/below zero, not a general leadership claim. Fixed control and all competing strategies remain in the full table.',fontsize=8)
fig.tight_layout(rect=(0,.07,1,.92));fig.savefig(OUT/'primary-reference-forest.svg',metadata={'Date':None});plt.close(fig)

def read(p):
 data=p.read_bytes();return json.loads(gzip.decompress(data) if p.suffix=='.gz' else data)
points=[]
for domain,model in ORDER:
 base=W/'validation'/domain
 if domain!='turkish':base/=model
 groups=[base/'baseline',base/'baseline-valid-96',base/'candidate-final-d0']
 for group in groups:
  p=group/'report.json.gz'
  if not p.exists():p=group/'report.json'
  if not p.exists():continue
  report=read(p)
  workloads=report['configuration']['dense_embeddings']['producer_metadata']['candidate_workloads']
  for c in report['candidates']:
   if c['status']!='ok':continue
   work=next(v for v in workloads if v['tool']==c['tool'] and v['chunk_capacity']==c['chunk_capacity'])
   points.append({'domain':domain,'model':model,'role':'candidate' if group.name=='candidate-final-d0' else 'baseline','tool':c['tool'],'capacity':c['chunk_capacity'],'recall':c['summary']['all']['evidence_at_budget']['recall'],'precision':c['summary']['all']['evidence_at_budget']['precision'],'vectors':c['chunks'],'native_passage_tokens':work['passage_input_tokens'],'unique_native_passage_tokens':work['unique_passage_input_tokens'],'report_sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
assert len(points)==125
with (OUT/'validation-quality-workload.csv').open('w',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(points[0]));writer.writeheader();writer.writerows(points)
fig,axes=plt.subplots(2,3,figsize=(13,7.4));flat=axes.flat
for axis,key in zip(flat,ORDER):
 subset=[p for p in points if (p['domain'],p['model'])==key]
 for p in sorted(subset,key=lambda p:p['role']=='candidate'):
  color=COLORS[p['tool']] if p['role']=='candidate' else '#111111' if p['tool']=='fixed' else '#aaaaaa'
  marker='o' if p['capacity']==64 else '^'
  axis.scatter(p['native_passage_tokens']/1000,p['recall'],c=color,marker=marker,s=34 if p['role']=='candidate' or p['tool']=='fixed' else 18,alpha=.85 if p['role']=='candidate' or p['tool']=='fixed' else .55)
 axis.set_title(LABELS[key],fontsize=10);axis.set_ylim(0,1);axis.grid(alpha=.15);axis.set_xlabel('Native passage tokens (thousands)');axis.set_ylabel('Evidence recall')
legend_ax=axes[1,2];legend_ax.axis('off')
handles=[Line2D([],[],color=color,marker='o',linestyle='',label=label) for color,label in [('#2166ac','Final structural profile'),('#e08214','Final prose compact'),('#1b9e77','Final code compact'),('#111111','Fixed control'),('#aaaaaa','Prior main and named strategies')]]
handles.extend([Line2D([],[],color='#555555',marker='o',linestyle='',label='64-token children'),Line2D([],[],color='#555555',marker='^',linestyle='',label='96-token children')]);legend_ax.legend(handles=handles,loc='center',frameon=False,fontsize=9)
fig.suptitle('Held-out quality and complete passage-token workload at 512 context tokens',fontsize=12)
fig.text(.01,.012,'Within-panel comparisons only: native tokenizers differ across models. All 125 successful source/candidate cells shown; five failed baseline cells remain explicit in the CSV/error ledger.\nCounts include complete native inputs with special tokens and duplicate payloads; unique-token work is also retained in the CSV. These are workload points, not elapsed-time or Pareto claims.',fontsize=8)
fig.tight_layout(rect=(0,.07,1,.94));fig.savefig(OUT/'validation-quality-workload.svg',metadata={'Date':None});plt.close(fig)
manifest={'rows_primary':len(rows),'successful_points':len(points),'inputs':{'validation/candidate-results-summary.json':hashlib.sha256((W/'validation/candidate-results-summary.json').read_bytes()).hexdigest(),'reference-choices-before-validation.json':hashlib.sha256((W/'reference-choices-before-validation.json').read_bytes()).hexdigest()},'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT/'primary-reference-points.csv',OUT/'primary-reference-forest.svg',OUT/'validation-quality-workload.csv',OUT/'validation-quality-workload.svg']}}
(OUT/'plot-audit.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'primary_rows':len(rows),'successful_points':len(points),'outputs':list(manifest['outputs'])}))
