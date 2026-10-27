from __future__ import annotations
import collections,hashlib,json,pathlib,unicodedata,io,tarfile,shutil
from cryptography.fernet import Fernet
P=pathlib.Path('/workspace/work/omnichunk-v3'); U=P/'upstream'
H=lambda b:hashlib.sha256(b).hexdigest()
N=lambda t:' '.join(unicodedata.normalize('NFC',t).split())
J=lambda p:json.loads(p.read_text())
protocol=J(P/'belebele_protocol.json');ns=protocol['namespace']
tr=[json.loads(z) for z in (U/'belebele-data-tur_Latn.jsonl').read_text().splitlines()]
en=[json.loads(z) for z in (U/'belebele-data-eng_Latn.jsonl').read_text().splitlines()]
oldtext=[];oldquery=set();oldmanifest=[]
for f in pathlib.Path('/workspace/omnichunk/benchmarks/retrieval').glob('corpus*/**/manifest.json'):
 j=J(f);oldmanifest.append({'path':str(f.relative_to('/workspace/omnichunk')),'sha256':H(f.read_bytes())})
 oldtext.extend(N((f.parent/d['path']).read_text()) for d in j['documents'])
 oldquery.update(N(q['text']).casefold() for q in j['queries'])
eng={(r['link'],r['question_number']):r for r in en}; groups=collections.defaultdict(list)
for row in tr:groups[row['link']].append(row)
eligible=[];excluded=[]
for link,rows in groups.items():
 assert len(set(N(r['flores_passage']) for r in rows))==1
 if len(rows)<2:continue
 e=eng[(link,rows[0]['question_number'])]
 vals=[N(rows[0]['flores_passage']),N(e['flores_passage'])]
 if any(v in old or old in v for v in vals for old in oldtext if len(old)>40):excluded.append(link);continue
 if any(N(r['question']).casefold() in oldquery or N(eng[(link,r['question_number'])]['question']).casefold() in oldquery for r in rows):excluded.append(link);continue
 eligible.append((link,rows))
eligible.sort(key=lambda p:(H((ns+p[0]).encode()),p[0])); selected=eligible[:min(120,len(eligible)//2*2)]
base={'schema_version':1,'corpus_id':'belebele-turkish-passage-v1','license':'CC-BY-SA-4.0','source':'https://huggingface.co/datasets/facebook/belebele','provenance':{'dataset_revision':protocol['revision'],'authors':'Belebele authors: Bandarkar et al., 2023; FLORES source contributors','upstream_sha256':H((U/'belebele-data-tur_Latn.jsonl').read_bytes()),'paired_english_sha256':H((U/'belebele-data-eng_Latn.jsonl').read_bytes()),'protocol_sha256':H((P/'belebele_protocol.json').read_bytes()),'evidence_policy':protocol['evidence_policy'],'limitations':protocol['limitations'],'previous_manifests':oldmanifest,'selection_namespace':ns,'source_link_grouping':'Each upstream link has exactly one unique passage; link disjointness is enforced.'},'documents':[],'queries':[]}
part={s:json.loads(json.dumps(base)) for s in ['dev','test']}; seenq={}; seenp={}
for i,(link,rows) in enumerate(selected):
 s='dev' if i%2==0 else 'test'; dest=P/'turkish'/('development' if s=='dev' else '_validation_plain');(dest/'documents').mkdir(parents=True,exist_ok=True)
 rows.sort(key=lambda r:(H((ns+link+str(r['question_number'])).encode()),r['question_number']))
 raw=rows[0]['flores_passage'].encode();sid='belebele-tr-'+H(link.encode())[:20]; fn='documents/'+sid+'.txt';(dest/fn).write_bytes(raw)
 assert N(raw.decode()) not in seenp or seenp[N(raw.decode())]==s;seenp[N(raw.decode())]=s
 part[s]['documents'].append({'source_id':sid,'path':fn,'sha256':H(raw),'language':'tr','category':'prose','split':s,'upstream_link':link,'attribution':'Belebele authors and original FLORES source contributors: '+link})
 for row in rows[:2]:
  qnorm=N(row['question']).casefold();assert qnorm not in seenq or seenq[qnorm]==s;seenq[qnorm]=s
  part[s]['queries'].append({'query_id':sid+'-q'+str(row['question_number']),'text':row['question'],'split':s,'evidence':[{'source_id':sid,'start':0,'end':len(raw),'quote':raw.decode()}],'upstream_question_number':row['question_number'],'upstream_link':link,'original_task':'multiple-choice reading comprehension adapted to passage retrieval'})
for s in part:
 dest=P/'turkish'/('development' if s=='dev' else '_validation_plain');(dest/'manifest.json').write_text(json.dumps(part[s],ensure_ascii=False,indent=2)+'\n');(dest/'NOTICE.md').write_text('Belebele Turkish subset, CC-BY-SA 4.0. Bandarkar et al. (2023), The Belebele Benchmark: a Parallel Reading Comprehension Dataset in 122 Language Variants. Original source links and contributors are attributed per document. https://huggingface.co/datasets/facebook/belebele\n');(dest/'LICENSE').write_text('CC-BY-SA-4.0\nhttps://creativecommons.org/licenses/by-sa/4.0/legalcode\n')
 # Exact-byte and manifest conformance checks.
 import sys;sys.path.insert(0,'/workspace/omnichunk');sys.path.insert(0,'/workspace/omnichunk/src');from benchmarks.retrieval.corpus import load_corpus
 c=load_corpus(dest);assert len(c.documents)==60 and len(c.queries)==120
validation=P/'turkish/_validation_plain'; buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tar:tar.add(validation,arcname='validation')
key=Fernet.generate_key(); blob=Fernet(key).encrypt(buf.getvalue());enc=P/'turkish/validation-sealed.fernet';enc.write_bytes(blob)
commitment={'protocol_sha256':H((P/'belebele_protocol.json').read_bytes()),'development_manifest_sha256':H((P/'turkish/development/manifest.json').read_bytes()),'validation_manifest_sha256':H((validation/'manifest.json').read_bytes()),'sealed_sha256':H(blob),'eligible_article_count':len(eligible),'excluded_oldsource_article_count':len(excluded),'selected_article_count':len(selected),'split_documents':60,'split_queries':120,'normalized_source_overlap':0,'normalized_question_overlap':0,'selection_uses_scores':False,'same_agent_custody':True}
(P/'turkish/commitment.json').write_text(json.dumps(commitment,indent=2)+'\n');shutil.rmtree(validation)
print(json.dumps({'key':key.decode(),'commitment':commitment}))
