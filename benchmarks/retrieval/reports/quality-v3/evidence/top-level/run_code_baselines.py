import os, subprocess,sys
from pathlib import Path
root=Path('/workspace/work/omnichunk-v3')
models=[('multilingual',Path('/workspace/work/omnichunk-dense/model-path.txt').read_text().strip(),'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','e8f8c211226b894fcb81acc59f3b34ba3efd5f42'),('english',Path('/workspace/work/omnichunk-quality/new-corpus/second-model/model-path.txt').read_text().strip(),'sentence-transformers/all-MiniLM-L6-v2','1110a243fdf4706b3f48f1d95db1a4f5529b4d41')]
for label,path,model,rev in models:
 cmd=[sys.executable,'/workspace/work/omnichunk-quality/matrix.py','--checkout',str(root/'baseline'),'--corpus',str(root/'code/development'),'--model-dir',path,'--model-id',model,'--model-sha',rev,'--tools','omnichunk,fixed,semchunk,langchain,semantic-text-splitter,llamaindex,chonkie-sentence,langchain-code,llamaindex-sentence','--output',str(root/'dev/code'/label/'baseline')]
 subprocess.run(cmd,env={**os.environ,'NLTK_DATA':str(root/'adapter-audit/nltk_data')},check=True)
