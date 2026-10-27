"""Public code-window regressions for measured units and canonical source bytes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest

from omnichunk import Chunker
from omnichunk.parser import tree_sitter
from omnichunk.types import Chunk, ChunkingError
from omnichunk.util.text_index import TextIndex
from omnichunk.windowing import models


def _assert_source(chunks: list[Chunk], source: str, limit: int, count: Callable[[str], int]):
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    cursor = 0
    for chunk in chunks:
        assert chunk.byte_range.start == cursor
        cursor = chunk.byte_range.end
        assert raw[chunk.byte_range.start : cursor].decode("utf-8") == chunk.text
        assert count(chunk.contextualized_text) <= limit
    assert cursor == len(raw)


@pytest.mark.parametrize("symbol", ["界", "😀"])
@pytest.mark.parametrize("unit", ["chars", "nws", "tokens"])
@pytest.mark.parametrize("fallback", [False, True])
def test_fitting_unicode_literal_is_not_split_by_utf8_byte_count(
    symbol, unit, fallback, monkeypatch
):
    if fallback:
        monkeypatch.setattr(tree_sitter, "get_ts_parser", lambda language: None)
    source = 'value = "' + symbol * 120 + '"\n'
    count = (
        (lambda text: len(text) // 4)
        if unit == "tokens"
        else (lambda text: sum(not char.isspace() for char in text))
        if unit == "nws"
        else len
    )
    capacity = 64 if unit == "tokens" else 256
    chunker = Chunker(
        max_chunk_size=capacity,
        min_chunk_size=0,
        size_unit=unit,
        tokenizer=count if unit == "tokens" else None,
        context_mode="none",
        coverage_policy="lossless",
    )

    chunks = chunker.chunk("literal.py", source)

    assert [chunk.text for chunk in chunks] == [source]
    _assert_source(chunks, source, capacity, count)
    streamed = list(chunker.stream("literal.py", source))
    assert [replace(chunk, total_chunks=len(streamed)) for chunk in streamed] == chunks


def test_fitting_unicode_functions_remain_whole_in_a_larger_source():
    functions = [f'def label_{index}():\n    return "' + "İ界😀" * 35 + '"\n' for index in range(3)]
    source = "\n".join(functions)
    chunks = Chunker(
        max_chunk_size=160,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("labels.py", source)

    _assert_source(chunks, source, 160, len)
    for function in functions:
        assert any(function in chunk.text for chunk in chunks)


def test_code_grouping_measures_inter_statement_whitespace():
    source = "alpha = 1\n\n\n\nbravo = 2\n"
    chunks = Chunker(
        max_chunk_size=16,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
        overflow_policy="error",
    ).chunk("assignments.py", source)

    _assert_source(chunks, source, 16, len)
    assert any("alpha = 1" in chunk.text for chunk in chunks)
    assert any("bravo = 2" in chunk.text for chunk in chunks)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_fitting_leading_comment_stays_with_following_statement(newline):
    previous = 'previous = "' + "x" * 28 + '"' + newline * 2
    policy = "# Return cached records only after access checks." + newline
    policy += "ALLOW_CACHE = False" + newline * 2
    following = 'next_value = "' + "y" * 28 + '"' + newline
    source = previous + policy + following
    chunker = Chunker(
        max_chunk_size=90,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk("policy.py", source)

    _assert_source(chunks, source, 90, len)
    assert any(policy in chunk.text for chunk in chunks)
    assert [chunk.text for chunk in chunker.stream("policy.py", source)] == [
        chunk.text for chunk in chunks
    ]


def test_comment_binding_counts_unicode_source_and_special_token_overhead():
    prefix = 'before = "' + "x" * 24 + '"\n\n'
    block = "# İzin 確認 😀\n# Keep the approval reason.\nAPPROVED = False\n\n"
    source = prefix + block + 'after = "' + "y" * 24 + '"\n'

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2

    chunks = Chunker(
        max_chunk_size=90,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 90, count)
    assert any(block in chunk.text for chunk in chunks)


@pytest.mark.parametrize(
    ("source", "capacity", "first"),
    [
        (
            "previous = 1  # previous note\nfollowing = 2\n",
            40,
            "previous = 1  # previous note\n",
        ),
        (
            'previous = "xxxxxxxx"\n# separate note\n\nfollowing = 2\n',
            45,
            'previous = "xxxxxxxx"\n# separate note\n\n',
        ),
    ],
)
def test_comment_binding_respects_inline_ownership_and_blank_lines(source, capacity, first):
    chunks = Chunker(
        max_chunk_size=capacity,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, capacity, len)
    assert chunks[0].text == first


def test_comment_binding_rechecks_nonadditive_complete_payload_budget():
    source = 'previous = "xxxxxxxx"\n# a policy comment\nVALUE = 2\n'

    def count(text: str) -> int:
        return len(text) + (100 if "# a policy" in text and "VALUE" in text else 0)

    chunks = Chunker(
        max_chunk_size=48,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 48, count)
    assert not any("# a policy" in chunk.text and "VALUE" in chunk.text for chunk in chunks)


def test_oversized_comment_does_not_hide_explicit_overflow_policies():
    source = "# " + "policy " * 15 + "\nVALUE = 2\n"
    arguments = dict(
        max_chunk_size=40,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = Chunker(**arguments).chunk("policy.py", source)
    _assert_source(chunks, source, 40, len)
    with pytest.raises(ChunkingError):
        Chunker(**arguments, overflow_policy="error").chunk("policy.py", source)
    preserved = Chunker(**arguments, overflow_policy="preserve").chunk("policy.py", source)
    assert "".join(chunk.text for chunk in preserved) == source
    assert max(len(chunk.text) for chunk in preserved) > 40


def test_code_grouping_measures_nonadditive_combined_token_cost():
    def count(text: str) -> int:
        return len(text) + (20 if "alpha" in text and "bravo" in text else 0)

    source = "alpha = 1\nbravo = 2\n"
    chunks = Chunker(
        max_chunk_size=20,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
        overflow_policy="error",
    ).chunk("assignments.py", source)

    _assert_source(chunks, source, 20, count)
    assert any("alpha = 1" in chunk.text for chunk in chunks)
    assert any("bravo = 2" in chunk.text for chunk in chunks)


def test_code_measures_a_whole_source_before_splitting_partial_tokens():
    source = "alpha = 1\nbravo = 2\n"

    def count(text: str) -> int:
        return 1 if text == source else len(text) * 2

    chunks = Chunker(
        max_chunk_size=1,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("assignments.py", source)

    assert [chunk.text for chunk in chunks] == [source]
    _assert_source(chunks, source, 1, count)


def test_code_rechecks_preferred_leaf_boundaries_with_nonmonotonic_counter():
    def count(text: str) -> int:
        return 100 if text.endswith(" ") else len(text)

    source = "# abcd efgh ijkl"
    chunks = Chunker(
        max_chunk_size=4,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.py", source)

    _assert_source(chunks, source, 4, count)
    assert chunks[0].text == "# ab"


@pytest.mark.parametrize("unit", ["chars", "nws", "tokens"])
def test_oversized_unicode_leaf_keeps_exact_source_and_actual_budget(unit):
    source = 'value = "' + "界😀İ" * 150 + '"\r\n'
    count = (
        (lambda text: len(text.encode("utf-8")))
        if unit == "tokens"
        else (lambda text: sum(not char.isspace() for char in text))
        if unit == "nws"
        else len
    )
    chunks = Chunker(
        max_chunk_size=48,
        min_chunk_size=0,
        size_unit=unit,
        tokenizer=count if unit == "tokens" else None,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("literal.py", source)

    _assert_source(chunks, source, 48, count)
    assert len(chunks) > 1


@pytest.mark.parametrize("policy", ["error", "preserve"])
def test_code_overflow_policy_applies_to_an_oversized_unicode_literal(policy):
    source = 'value = "' + "界😀" * 40 + '"\n'
    chunker = Chunker(
        max_chunk_size=30,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
        overflow_policy=policy,
    )
    if policy == "error":
        with pytest.raises(ChunkingError, match="exceeds"):
            chunker.chunk("literal.py", source)
    else:
        chunks = chunker.chunk("literal.py", source)
        assert "".join(chunk.text for chunk in chunks) == source
        assert any(chunk.metadata["budget"]["overflow"] > 0 for chunk in chunks)


def test_nws_oversized_code_does_not_probe_shrinking_source_suffixes(monkeypatch):
    def reject_suffix_probes(*args, **kwargs):
        pytest.fail("NWS fitting must use its cumulative index, not suffix counter probes")

    monkeypatch.setattr(models, "find_fitting_prefix", reject_suffix_probes)
    source = 'value = "' + "界\u2003😀\u00a0" * 1000 + '"\n'
    chunks = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="nws",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("unicode.py", source)

    _assert_source(chunks, source, 64, lambda text: sum(not char.isspace() for char in text))
    assert len(chunks) > 10


@pytest.mark.parametrize("source", ["a b\n c", "\u00a0界\u2003😀\u3000İ\t "])
def test_nws_index_measures_unicode_subranges_and_maximal_fitting_ends(source):
    def reject_rescans(text):
        pytest.fail("NWS subrange queries must not rescan source strings")

    index = TextIndex(source)
    budget = models.SourceBudget(source, index, reject_rescans, size_unit="nws")
    for start in range(len(source)):
        for end in range(start + 1, len(source) + 1):
            start_b, end_b = index.byte_offset_for_char(start), index.byte_offset_for_char(end)
            expected = sum(not char.isspace() for char in source[start:end])
            assert budget.count(start_b, end_b) == expected
            for limit in (1, 2, 5):
                fitting = max(
                    stop
                    for stop in range(start, end + 1)
                    if sum(not char.isspace() for char in source[start:stop]) <= limit
                )
                assert budget.fitting_end(start_b, end_b, limit) == index.byte_offset_for_char(
                    fitting
                )
