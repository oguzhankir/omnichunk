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


# ---------------------------------------------------------------------------
# Commit 32 — heuristic segmentation quality (15 regression tests)
# ---------------------------------------------------------------------------


def _texts(text: str) -> list[str]:
    return [p.text for p in extract_propositions_heuristic("f.md", text)]


def _slice_ok(text: str) -> bool:
    raw = text.encode("utf-8")
    for p in extract_propositions_heuristic("f.md", text):
        if raw[p.byte_range.start : p.byte_range.end].decode("utf-8") != p.text:
            return False
    return True


# (1) Parenthetical asides must not create a boundary.
def test_parenthetical_aside_single_proposition() -> None:
    text = "The result (see Figure 3) is significant."
    props = _texts(text)
    assert len(props) == 1
    assert "(see Figure 3)" in props[0]


def test_parenthetical_with_inner_period_not_split() -> None:
    text = "The model (v2.0 was released) works well."
    props = _texts(text)
    assert len(props) == 1


def test_parenthetical_with_inner_semicolon_not_split() -> None:
    text = "A tuple (a; b; c) is shown here."
    props = _texts(text)
    assert len(props) == 1


# (2) Numbered lists produce one proposition per item.
def test_numbered_list_one_proposition_per_item() -> None:
    text = "Steps:\n1. Boil water.\n2. Add pasta.\n3. Drain it."
    props = _texts(text)
    joined = " ".join(props)
    assert "Boil water." in joined
    assert "Add pasta." in joined
    assert "Drain it." in joined
    item_props = [p for p in props if p.lstrip()[:2] in {"1.", "2.", "3."}]
    assert len(item_props) == 3


def test_numbered_list_without_trailing_periods() -> None:
    text = "1. First item\n2. Second item\n3. Third item"
    props = _texts(text)
    assert any("First item" in p for p in props)
    assert any("Second item" in p for p in props)
    assert any("Third item" in p for p in props)
    assert len(props) == 3


def test_numbered_list_marker_period_not_decimal_boundary() -> None:
    text = "1. Alpha\n2. Beta"
    assert _slice_ok(text)
    assert len(_texts(text)) == 2


# (3) Semicolon-separated clauses split into separate propositions.
def test_semicolon_splits_two_clauses() -> None:
    text = "Cats are felines; dogs are canines."
    props = _texts(text)
    assert len(props) == 2
    assert any("Cats are felines" in p for p in props)
    assert any("dogs are canines" in p for p in props)


def test_semicolon_splits_three_clauses() -> None:
    text = "X is one; Y is two; Z is three."
    props = _texts(text)
    assert len(props) == 3


def test_semicolon_in_parens_not_split() -> None:
    text = "The set (x; y) is defined; it has two members."
    props = _texts(text)
    assert len(props) == 2


# (4) Quoted speech must not split at internal punctuation.
def test_quoted_comma_not_split() -> None:
    text = '"The cat sat," she said.'
    props = _texts(text)
    assert len(props) == 1


def test_quoted_period_not_split() -> None:
    text = 'She said "Hello. Goodbye." and then left.'
    props = _texts(text)
    assert len(props) == 1


def test_quoted_semicolon_not_split() -> None:
    text = 'He typed "a; b; c" into the box today.'
    props = _texts(text)
    assert len(props) == 1


# (5) Decimal points must not split mathematical expressions.
def test_decimal_value_not_split() -> None:
    text = "The value is 3.14 today."
    props = _texts(text)
    assert len(props) == 1
    assert "3.14" in props[0]


def test_multiple_decimals_not_split() -> None:
    text = "Versions 2.0 and 3.5 both shipped."
    props = _texts(text)
    assert len(props) == 1


def test_decimal_terminal_period_still_ends_sentence() -> None:
    text = "Pi is 3.14. Tau is double that."
    props = _texts(text)
    assert len(props) == 2
    assert _slice_ok(text)
