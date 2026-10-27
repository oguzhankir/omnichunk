"""Development-only source expansion; stored anchors, no model inference."""
from __future__ import annotations

import bisect
from dataclasses import asdict, dataclass
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
RUNTIME = Path('/workspace/work/omnichunk-v3/frozen-candidate-v3')
sys.path[:0] = [str(RUNTIME), str(RUNTIME/'src')]

from benchmarks.retrieval.corpus import load_corpus
from benchmarks.retrieval.tokenization import benchmark_counter
from omnichunk import Chunker, EvidenceSpan, score_evidence
from transformers import AutoTokenizer


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Span:
    source_id: str
    start: int
    end: int


class Document:
    def __init__(self, source_id: str, text: str, tokenizer, counter):
        self.source_id = source_id
        self.text = text
        self.raw = text.encode('utf-8')
        self.char_bytes = [0]
        for char in text:
            self.char_bytes.append(self.char_bytes[-1] + len(char.encode('utf-8')))
        self.byte_chars = {value: index for index, value in enumerate(self.char_bytes)}
        encoded = tokenizer(text, add_special_tokens=False, truncation=False,
                            return_offsets_mapping=True)
        self.offsets = [tuple(pair) for pair in encoded['offset_mapping']]
        self.starts = [start for start, _ in self.offsets]
        self.ends = [end for _, end in self.offsets]
        assert self.starts == sorted(self.starts) and self.ends == sorted(self.ends)
        self.counter = counter
        self.specials = counter('')

    def payload(self, span: Span) -> str:
        assert span.source_id == self.source_id
        assert span.start in self.byte_chars and span.end in self.byte_chars
        assert 0 <= span.start < span.end <= len(self.raw)
        return self.raw[span.start:span.end].decode('utf-8')

    @lru_cache(maxsize=None)
    def window(self, start: int, end: int, target: int) -> Span:
        anchor = Span(self.source_id, start, end)
        anchor_text = self.payload(anchor)
        assert self.counter(anchor_text) <= target
        if not self.offsets:
            return anchor
        a, b = self.byte_chars[start], self.byte_chars[end]
        left = min(len(self.offsets)-1, bisect.bisect_right(self.ends, a))
        right = max(left+1, bisect.bisect_left(self.starts, b))
        right = min(len(self.offsets), right)
        capacity = max(1, target-self.specials)
        extra = max(0, capacity-(right-left))
        lo = max(0, left-extra//2)
        hi = min(len(self.offsets), lo+capacity)
        lo = max(0, min(lo, hi-capacity))
        hi = max(right, hi)
        lo = min(left, lo)
        while True:
            first = 0 if lo == 0 else self.offsets[lo][0]
            last = len(self.text) if hi == len(self.offsets) else self.offsets[hi-1][1]
            first, last = min(a, first), max(b, last)
            candidate = Span(self.source_id, self.char_bytes[first], self.char_bytes[last])
            if self.counter(self.payload(candidate)) <= target:
                return candidate
            left_margin, right_margin = left-lo, hi-right
            if not left_margin and not right_margin:
                return anchor
            if left_margin > right_margin:
                lo += 1
            else:
                hi -= 1


def merged(existing: list[Span], extra: Span) -> list[Span]:
    lo, hi = extra.start, extra.end
    affected: set[int] = set()
    while True:
        found = {i for i, span in enumerate(existing)
                 if span.source_id == extra.source_id and span.start <= hi and lo <= span.end}
        if found <= affected:
            break
        affected |= found
        lo = min([lo, *(existing[i].start for i in affected)])
        hi = max([hi, *(existing[i].end for i in affected)])
    value = Span(extra.source_id, lo, hi)
    if not affected:
        return [*existing, value]
    first = min(affected)
    return [value if i == first else span for i, span in enumerate(existing)
            if i == first or i not in affected]


def assemble(windows: list[Span], documents: dict[str, Document], counter, budget=512):
    selected: list[Span] = []
    for window in windows:
        proposed = merged(selected, window)
        if proposed == selected:
            continue
        payload = '\n\n'.join(documents[span.source_id].payload(span) for span in proposed)
        if counter(payload) > budget:
            break
        selected = proposed
    text = '\n\n'.join(documents[span.source_id].payload(span) for span in selected)
    used = counter(text) if selected else 0
    assert used <= budget
    return selected, used


def main():
    output = HERE/'results.json.gz'
    if output.exists():
        raise ValueError('Never replace completed experiment')
    report_path = Path('/workspace/work/omnichunk-v3/validation/code-files/multilingual/baseline/report.json.gz')
    corpus_path = Path('/workspace/work/omnichunk-v3/code-files/validation')
    report = json.loads(gzip.decompress(report_path.read_bytes()))
    corpus = load_corpus(corpus_path)
    assert corpus.manifest_hash == report['corpus_manifest_sha256']
    snapshot = report['configuration']['tokenizer']
    count = lru_cache(maxsize=100_000)(benchmark_counter('tokens', snapshot, include_special_tokens=True))
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    documents = {doc.source_id: Document(doc.source_id, doc.text, tokenizer, count)
                 for doc in corpus.documents if doc.split == 'test'}
    raw_docs = {doc.source_id: doc for doc in corpus.documents if doc.split == 'test'}
    candidates = {(c['tool'], c['chunk_capacity']): c for c in report['candidates']}
    hierarchy: dict[tuple[int, str], dict] = {}
    construction = []
    for capacity in [64, 96]:
        c = candidates['omnichunk', capacity]
        reference = {(p['source_id'], p['start'], p['end'], p['text']) for p in c['passages']}
        matched = total_leaves = 0
        started = time.perf_counter()
        for source_id, doc in raw_docs.items():
            tree = Chunker(size_unit='tokens', tokenizer=count, context_mode='none',
                           coverage_policy='retrieval').hierarchical_chunk(
                               doc.path, doc.text, source_id=source_id,
                               levels=[capacity, 128, 256, 512])
            leaves = tree.leaves()
            exact: dict[tuple[int, int, str], dict[int, Span]] = {}
            for leaf in leaves:
                key = (source_id, leaf.byte_range.start, leaf.byte_range.end, leaf.text)
                matched += key in reference
                total_leaves += 1
                parents = {}
                current = leaf
                for target in [128,256,512]:
                    current = tree.parent(current)
                    assert current is not None
                    span = Span(source_id, current.byte_range.start, current.byte_range.end)
                    assert documents[source_id].payload(span) == current.text
                    assert count(current.text) <= target
                    parents[target] = span
                exact[key[1:]] = parents
            levels = {}
            for level, target in [(1,128),(2,256),(3,512)]:
                values = [Span(source_id, chunk.byte_range.start, chunk.byte_range.end)
                          for chunk in tree.at_level(level)]
                for span in values:
                    assert count(documents[source_id].payload(span)) <= target
                levels[target] = values
            hierarchy[capacity, source_id] = {'exact':exact, 'levels':levels}
        construction.append({'capacity':capacity,'indexed_baseline_passages':c['chunks'],
                             'native_hierarchy_leaves':total_leaves,'exact_baseline_leaf_matches':matched,
                             'construction_seconds_concurrent_diagnostic':time.perf_counter()-started})
    outputs=[]
    for (tool, capacity), candidate in candidates.items():
        if candidate['status'] != 'ok':
            continue
        for method, target in [('raw-prefix',512),('raw-top1',capacity),
                               *[('source-window',v) for v in [128,256,512]],
                               *([('public-hierarchy',v) for v in [128,256,512]] if tool.startswith('omnichunk') else [])]:
            rows=[]
            for q in candidate['per_query']:
                anchors = [Span(p['source_id'], p['start'], p['end']) for p in q['ranks']]
                mapping={'native_leaf':0,'containing_parent':0,'source_window_fallback':0}
                if method == 'raw-prefix':
                    by_id={p['passage_id']:p for p in candidate['passages']}
                    selected=[Span(by_id[k]['source_id'],by_id[k]['start'],by_id[k]['end']) for k in q['budget_passage_ids']]
                    used=q['budget_used']
                elif method == 'raw-top1':
                    selected=anchors[:1];used=count(documents[selected[0].source_id].payload(selected[0])) if selected else 0
                else:
                    windows=[]
                    for anchor in anchors:
                        doc=documents[anchor.source_id]
                        if method == 'source-window':
                            window=doc.window(anchor.start,anchor.end,target)
                        else:
                            h=hierarchy[capacity,anchor.source_id]
                            parents=h['exact'].get((anchor.start,anchor.end,doc.payload(anchor)))
                            if parents:
                                window=parents[target];mapping['native_leaf']+=1
                            else:
                                possible=[s for s in h['levels'][target] if s.start<=anchor.start and anchor.end<=s.end]
                                if possible:
                                    window=min(possible,key=lambda s:(s.end-s.start,s.start));mapping['containing_parent']+=1
                                else:
                                    window=doc.window(anchor.start,anchor.end,target);mapping['source_window_fallback']+=1
                        windows.append(window)
                    selected,used=assemble(windows,documents,count)
                metrics=asdict(score_evidence([EvidenceSpan(s.source_id,s.start,s.end) for s in selected],
                                             [EvidenceSpan(**s) for s in q['evidence']]))
                rows.append({'query_id':q['query_id'],'metrics':metrics,'budget_used':used,
                             'spans':[asdict(s) for s in selected],'mapping':mapping,
                             'top1_source_hit':bool(anchors and anchors[0].source_id in {s['source_id'] for s in q['evidence']})})
                if method == 'raw-prefix':
                    assert metrics==q['evidence_at_budget']
            summary={key:statistics.mean(row['metrics'][key] for row in rows) for key in ['precision','recall','iou']}
            outputs.append({'tool':tool,'capacity':capacity,'method':method,'expansion_target':target,
                            'summary':summary,'queries':len(rows),'child_vectors':candidate['chunks'],
                            'mean_budget_used':statistics.mean(row['budget_used'] for row in rows),
                            'mapping_counts':{key:sum(row['mapping'][key] for row in rows) for key in ['native_leaf','containing_parent','source_window_fallback']},
                            'rows':rows})
            print(tool,capacity,method,target,summary,flush=True)
    result={'schema_version':1,'protocol_sha256':digest(HERE.parent.parent/'protocol.json'),'protocol_addendum_sha256':digest(HERE.parent/'protocol-addendum.json'),
            'script_sha256':digest(Path(__file__)),'input_report_sha256':digest(report_path),
            'corpus_manifest_sha256':corpus.manifest_hash,'runtime_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=RUNTIME,text=True).strip(),
            'native_tokenizer':snapshot,'context_budget':512,'model_calls':0,'rank_calls':0,
            'hierarchy_construction':construction,'outputs':outputs,
            'limitations':['Secondary held-out stress execution of fixed workflow grid; no parameter or source/profile change', 'Whole-file view shares held-out questions with isolated-function view, not independent evidence', 'Documentation summaries are proxy queries and whole-function gold is not dependency-complete', 'All baseline rival raw and source-window controls retained; no selected winning-workflow or broad superiority claim', 'Native index identity and cache coverage must be re-audited on these validation inputs', 'No isolated latency or memory claim from concurrent diagnostic construction timings']}
    with output.open('wb') as f, gzip.GzipFile(fileobj=f,filename='',mtime=0,mode='wb') as z:
        z.write((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    brief={key:value for key,value in result.items() if key!='outputs'}
    brief['outputs']=[{key:value for key,value in row.items() if key!='rows'} for row in outputs]
    (HERE/'summary.json').write_text(json.dumps(brief,indent=2)+'\n')
    print(json.dumps({'outputs':len(outputs),'path':str(output),'sha256':digest(output)}),flush=True)


if __name__=='__main__':
    main()
