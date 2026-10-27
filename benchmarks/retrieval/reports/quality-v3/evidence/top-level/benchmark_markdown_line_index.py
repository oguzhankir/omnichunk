"""Manual scaling evidence, never a timing assertion in the test suite."""
import argparse,hashlib,json,statistics,subprocess,time
from pathlib import Path
from omnichunk.parser.markdown_parser import parse_markdown
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=2);a=p.parse_args()
rows=[]
for size in (10000,20000):
 source=('A paragraph '+('explanation '*7)+'ends here.\n\n')*size
 samples=[]
 for _ in range(a.repeats):
  started=time.perf_counter();_,nodes=parse_markdown(source);samples.append(time.perf_counter()-started)
  assert len(nodes)==size
  assert ''.join(n.text for n in nodes)==source
 rows.append({'paragraphs':size,'source_utf8_bytes':len(source.encode()),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'samples_seconds':samples,'median_seconds':statistics.median(samples),'nodes':len(nodes)})
result={'runtime_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'runtime_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),'measurement':'manual parse-only same-machine scaling; no timing-based test assertion','rows':rows,'20k_to_10k_ratio':rows[1]['median_seconds']/rows[0]['median_seconds']}
a.output.write_text(json.dumps(result,indent=2)+'\n');print(result)
