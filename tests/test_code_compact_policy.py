"""Compact code packing is explicit, measured and preserves fitting definitions."""

from __future__ import annotations

import pytest

from omnichunk import Chunker

SOURCE = (
    "def collect(items):\n"
    "    first = normalize(items)\n"
    "    second = apply(first)\n"
    "    third = produce(second)\n"
    "    return third\n"
)


def test_compact_policy_selects_fewer_more_balanced_fragments():
    chunker = Chunker(max_chunk_size=60, min_chunk_size=0, context_mode="none")
    structural = chunker.chunk("collect.py", SOURCE)
    compact = chunker.chunk("collect.py", SOURCE, code_boundary_policy="compact")
    assert len(structural) == 3 and len(compact) == 2
    assert [len(chunk.text) for chunk in compact] == [60, 60]
    assert "".join(chunk.text for chunk in compact) == SOURCE
    assert len(chunker.chunk("collect.py", SOURCE)) == 3
    assert structural[0].config_fingerprint != compact[0].config_fingerprint


def test_fitting_definitions_and_documented_root_groups_remain_whole():
    first = "# Read units.\ndef first():\n    return 1  # audited\n\n"
    second = "# Write units.\ndef second():\n    return 2\n"
    source = first + second
    chunks = Chunker(
        max_chunk_size=60,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        code_boundary_policy="compact",
    ).chunk("functions.py", source)
    assert [chunk.text for chunk in chunks] == [first, second]


@pytest.mark.parametrize("unit", ["chars", "nws", "tokens"])
def test_compact_preserves_native_budget_utf8_ranges_and_stream_parity(unit):
    source = (
        "def görev(öğe):\r\n"
        "    ilk = dönüştür(öğe)\r\n"
        "    ikinci = kaydet(ilk)\r\n"
        "    return ikinci\r\n"
    )

    def count(text):
        return len(text.encode("utf-8")) + 2 + (11 if "ilk" in text and "ikinci" in text else 0)

    chunker = Chunker(
        max_chunk_size=65,
        min_chunk_size=0,
        size_unit=unit,
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
        code_boundary_policy="compact",
    )
    chunks = chunker.chunk("functions.py", source)
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    for chunk in chunks:
        assert raw[chunk.byte_range.start : chunk.byte_range.end].decode("utf-8") == chunk.text
        measured = (
            count(chunk.text)
            if unit == "tokens"
            else (len(chunk.text) if unit == "chars" else sum(not c.isspace() for c in chunk.text))
        )
        assert measured <= 65
    assert [chunk.text for chunk in chunker.stream("functions.py", source)] == [
        chunk.text for chunk in chunks
    ]


@pytest.mark.parametrize("policy", ["error", "preserve"])
def test_compact_does_not_override_explicit_overflow_policy(policy):
    from omnichunk import ChunkingError

    args = dict(
        max_chunk_size=60,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        overflow_policy=policy,
    )
    if policy == "error":
        with pytest.raises(ChunkingError):
            Chunker(**args, code_boundary_policy="compact").chunk("collect.py", SOURCE)
    else:
        default = Chunker(**args).chunk("collect.py", SOURCE)
        compact = Chunker(**args, code_boundary_policy="compact").chunk("collect.py", SOURCE)
        assert [chunk.text for chunk in default] == [chunk.text for chunk in compact]


def test_invalid_compact_policy_is_rejected():
    with pytest.raises(ValueError, match="code_boundary_policy"):
        Chunker(code_boundary_policy="invalid")


def test_compact_fragment_entities_remain_marked_partial_when_context_enabled():
    chunks = Chunker(
        max_chunk_size=60,
        min_chunk_size=0,
        context_mode="full",
        code_boundary_policy="compact",
        coverage_policy="lossless",
    ).chunk("collect.py", SOURCE)
    assert "".join(chunk.text for chunk in chunks) == SOURCE
    assert all(any(entity.is_partial for entity in chunk.context.entities) for chunk in chunks)
    assert all(len(chunk.contextualized_text) <= 60 for chunk in chunks)


def test_structural_layout_cannot_win_by_dividing_a_fitting_protected_definition():
    from omnichunk.util.text_index import TextIndex
    from omnichunk.windowing.compact import compact_code_ranges
    from omnichunk.windowing.models import SourceBudget

    source = "abcdefghijklmnopqrst"
    result = compact_code_ranges(
        [(0, 10), (10, 20)],
        budget=SourceBudget(source, TextIndex(source), len, size_unit="chars"),
        max_size=10,
        protected=[(5, 15)],
    )
    assert result == [(0, 5), (5, 15), (15, 20)]
