"""Bind every retained workflow and per-query result row without rescoring."""
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def main():
    output = HERE/'row-hashes.json.gz'
    if output.exists():
        raise ValueError('Preserve existing row hashes')
    source = HERE/'combined-results.json.gz'
    result = json.loads(gzip.decompress(source.read_bytes()))
    records = []
    count = 0
    for workflow in result['outputs']:
        record = {key:workflow[key] for key in ['version','tool','capacity','method','expansion_target']}
        record['workflow_row_sha256'] = sha(workflow)
        record['query_rows'] = [{'query_id':row['query_id'],'sha256':sha(row)} for row in workflow['rows']]
        expected = 56 if workflow['status']=='ok' else 0
        assert len({r['query_id'] for r in record['query_rows']}) == len(workflow['rows']) == expected
        count += len(workflow['rows'])
        records.append(record)
    assert len(records) == 154 and count == 8344
    data = {'combined_results_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'canonicalization':'SHA256 UTF8 compact JSON sortedkeys ensure_ascii=False allow_nan=False','workflow_rows':154,'successful_workflow_rows':149,'explicit_failed_workflow_rows':5,'per_query_rows':8344,'unavailable_per_query_rows_due_to_frozen_adapter_failure':280,'rows':records}
    with output.open('xb') as f,gzip.GzipFile(fileobj=f,filename='',mtime=0,mode='wb') as z:
        z.write((json.dumps(data,indent=2)+'\n').encode())
    print(json.dumps({'workflow_rows':154,'per_query_rows':8344,'row_hashes_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}),flush=True)


if __name__=='__main__':
    main()
