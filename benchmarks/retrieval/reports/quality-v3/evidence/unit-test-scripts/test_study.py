import importlib.util
from pathlib import Path
import sys

spec=importlib.util.spec_from_file_location('parent_study',Path(__file__).with_name('study.py'))
study=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=study
spec.loader.exec_module(study)


class Characters:
    def __call__(self,text,**kwargs):
        return {'offset_mapping':[(i,i+1) for i in range(len(text))]}


def counter(text):
    return len(text)+2


def test_window_preserves_utf8_anchor_and_full_budget():
    text='önce abc\nİstanbul sonra son'
    doc=study.Document('a',text,Characters(),counter)
    a=text.index('İstanbul');b=a+len('İstanbul')
    window=doc.window(len(text[:a].encode()),len(text[:b].encode()),14)
    assert doc.payload(window).find('İstanbul')>=0
    assert counter(doc.payload(window))<=14
    assert window.start<=len(text[:a].encode())
    assert window.end>=len(text[:b].encode())


def test_merging_is_transitive_and_keeps_earliest_rank_position():
    spans=[study.Span('a',0,5),study.Span('b',0,8),study.Span('a',10,15)]
    assert study.merged(spans,study.Span('a',5,10))==[study.Span('a',0,15),study.Span('b',0,8)]


def test_prefix_assembly_stops_without_skipping_and_counts_separators():
    docs={key:study.Document(key,'x'*80,Characters(),counter) for key in ['a','b','c']}
    spans=[study.Span('a',0,40),study.Span('b',0,40),study.Span('c',0,1)]
    selected,used=study.assemble(spans,docs,counter,50)
    assert selected==spans[:1]
    assert used==42


def test_overlapping_windows_are_counted_as_union_not_duplicate_payloads():
    docs={'a':study.Document('a','x'*80,Characters(),counter)}
    selected,used=study.assemble([study.Span('a',0,30),study.Span('a',20,45)],docs,counter,50)
    assert selected==[study.Span('a',0,45)]
    assert used==47
