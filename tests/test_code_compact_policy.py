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


def test_compact_ties_prefer_filling_the_earlier_payload():
    chunks = Chunker(
        max_chunk_size=70,
        min_chunk_size=0,
        context_mode="none",
        code_boundary_policy="compact",
        coverage_policy="lossless",
    ).chunk("collect.py", SOURCE)
    assert [len(chunk.text) for chunk in chunks] == [70, 50]
    assert "".join(chunk.text for chunk in chunks) == SOURCE


def test_compact_token_probe_work_grows_with_source_not_remaining_suffixes():
    from omnichunk.util.text_index import TextIndex
    from omnichunk.windowing.compact import compact_code_ranges
    from omnichunk.windowing.models import SourceBudget

    capacity = 64

    def measured_work(length):
        source = "x" * length
        probes = []

        def count(text):
            probes.append(len(text))
            return len(text) + 2  # Complete inputs include special-token overhead.

        structural = [
            (start, min(start + capacity - 2, length)) for start in range(0, length, capacity - 2)
        ]
        budget = SourceBudget(source, TextIndex(source), count)
        ranges = compact_code_ranges(structural, budget=budget, max_size=capacity, protected=[])
        assert "".join(source[start:end] for start, end in ranges) == source
        assert all(count(source[start:end]) <= capacity for start, end in ranges)
        # One whole-source measurement estimates the candidate fragment count.
        # Subsequent probes stay near the budget, independent of file length.
        assert probes[0] == length
        assert max(probes[1:]) <= 2 * capacity
        return sum(probes)

    small = measured_work(8192)
    large = measured_work(16384)
    assert large <= 2.2 * small


def test_incremental_token_probe_recovers_a_later_nonadditive_completion():
    from omnichunk.util.text_index import TextIndex
    from omnichunk.windowing.models import SourceBudget

    token = "界😀complete"
    source = token + "x" * 100

    def count(text):
        return 1 if text == token else len(text) + 2

    budget = SourceBudget(source, TextIndex(source), count)
    end = budget.fitting_end(0, len(source.encode("utf-8")), 1, incremental=True)
    assert end == len(token.encode("utf-8"))
    assert budget.count(0, end) == 1


def test_incremental_token_probe_keeps_a_protected_unit_beyond_its_first_bracket():
    from omnichunk.util.text_index import TextIndex
    from omnichunk.windowing.compact import compact_code_ranges
    from omnichunk.windowing.models import SourceBudget

    prefix = "abc"
    unit = "BEGIN" + "界😀" * 80 + "END"
    source = prefix + unit + "z" * 200
    index = TextIndex(source)

    def count(text):
        return len(text.replace(unit, "")) + (5 if unit in text else 0) + 2

    structural = [
        (
            index.byte_offset_for_char(start),
            index.byte_offset_for_char(min(start + 62, len(source))),
        )
        for start in range(0, len(source), 62)
    ]
    left = len(prefix.encode("utf-8"))
    right = len((prefix + unit).encode("utf-8"))
    budget = SourceBudget(source, index, count)
    ranges = compact_code_ranges(structural, budget=budget, max_size=64, protected=[(left, right)])
    assert ranges[0][1] >= right
    assert all(not left < end < right for _, end in ranges)
    raw = source.encode("utf-8")
    assert b"".join(raw[start:end] for start, end in ranges) == raw
    assert all(budget.count(start, end) <= 64 for start, end in ranges)


def test_incremental_token_probe_with_no_fitting_character_keeps_overflow_explicit():
    from omnichunk import ChunkingError

    with pytest.raises(ChunkingError):
        Chunker(
            max_chunk_size=1,
            min_chunk_size=0,
            size_unit="tokens",
            tokenizer=lambda text: len(text) + 2,
            context_mode="none",
            coverage_policy="lossless",
            code_boundary_policy="compact",
        ).chunk("tiny.py", "value = 1\n")


def test_compact_rejects_unsafe_fallback_when_nonadditive_counter_prevents_atomic_layout():
    from omnichunk import ChunkingError
    from omnichunk.util.text_index import TextIndex
    from omnichunk.windowing.compact import compact_code_ranges
    from omnichunk.windowing.models import SourceBudget

    source = "0123456789ABCDEFGHIJ"

    def count(text):
        if text == "01234":
            return 11
        if text == "3456789ABCDE":
            return 10
        return len(text)

    with pytest.raises(ChunkingError, match="code_boundary_policy='structure'"):
        compact_code_ranges(
            [(0, 10), (10, 20)],
            budget=SourceBudget(source, TextIndex(source), count, size_unit="tokens"),
            max_size=10,
            protected=[(5, 15)],
        )


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("blank_lines", [0, 1])
def test_fitting_definitions_stay_whole_when_trailing_trivia_needs_its_own_chunk(
    newline, blank_lines
):
    first = newline.join(["def first():", "    return 1"])
    second = newline.join(["def second():", "    return 2"])
    source = first + newline * (blank_lines + 1) + second + newline
    limit = max(len(first), len(second))
    chunks = Chunker(
        max_chunk_size=limit,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        code_boundary_policy="compact",
    ).chunk("functions.py", source)
    assert any(first in chunk.text for chunk in chunks)
    assert any(second in chunk.text for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks) == source
    assert all(len(chunk.contextualized_text) <= limit for chunk in chunks)
