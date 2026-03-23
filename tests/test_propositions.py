from __future__ import annotations

import json

import pytest

from omnichunk import Chunker
from omnichunk.propositions.heuristic import extract_propositions_heuristic


def test_heuristic_propositions_byte_slice_invariant() -> None:
    text = "Python is a language.\n\nThe MIT license applies in 2024."
    props = extract_propositions_heuristic("doc.md", text)
    raw = text.encode("utf-8")
    for p in props:
        got = raw[p.byte_range.start : p.byte_range.end].decode("utf-8")
        assert got == p.text


def test_heuristic_deterministic() -> None:
    text = "Alpha is a test. Beta is another.\n"
    a = extract_propositions_heuristic("f.md", text)
    b = extract_propositions_heuristic("f.md", text)
    assert [p.text for p in a] == [p.text for p in b]
    assert [p.byte_range for p in a] == [p.byte_range for p in b]


def test_chunker_extract_propositions_heuristic() -> None:
    c = Chunker()
    text = "Omnichunk is a chunking library."
    props = c.extract_propositions("x.md", text, mode="heuristic")
    assert isinstance(props, list)


def test_extract_propositions_llm_mock() -> None:
    c = Chunker()
    text = "Claim one. Claim two here."

    def llm_fn(_fp: str, _t: str) -> str:
        return json.dumps({"claims": [{"text": "Claim one."}, {"text": "Claim two here."}]})

    props = c.extract_propositions("z.md", text, mode="llm", llm_fn=llm_fn)
    assert len(props) == 2
    raw = text.encode("utf-8")
    for p in props:
        assert raw[p.byte_range.start : p.byte_range.end].decode("utf-8") == p.text


def test_extract_propositions_llm_requires_fn() -> None:
    c = Chunker()
    with pytest.raises(ValueError, match="llm_fn"):
        c.extract_propositions("z.md", "hi", mode="llm")
