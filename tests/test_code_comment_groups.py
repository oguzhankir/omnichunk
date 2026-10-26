"""Source-preserving isolation of documented root statements."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from omnichunk import Chunker
from omnichunk.types import Chunk


def _assert_source(chunks: list[Chunk], source: str, limit: int, count: Callable[[str], int]):
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    cursor = 0
    for chunk in chunks:
        assert chunk.byte_range.start == cursor
        cursor = chunk.byte_range.end
        assert raw[chunk.byte_range.start : cursor].decode("utf-8") == chunk.text
        assert count(chunk.text) <= limit
    assert cursor == len(raw)


@pytest.mark.parametrize("minimum", [0, 90])
def test_independent_documented_policies_are_distinct_despite_soft_minimum(minimum):
    prefix = 'prefix = "' + "x" * 45 + '"\n\n'
    first = "# Enable audited reads only.\nAUDIT_READS = True\n\n"
    second = "# Keep revoked sessions disabled.\nALLOW_REVOKED = False\n\n"
    suffix = 'suffix = "' + "y" * 45 + '"\n'
    source = prefix + first + second + suffix
    chunker = Chunker(
        max_chunk_size=120,
        min_chunk_size=minimum,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk("policy.py", source)

    _assert_source(chunks, source, 120, len)
    assert [chunk.text for chunk in chunks] == [prefix, first, second, suffix]
    assert [chunk.text for chunk in chunker.stream("policy.py", source)] == [
        chunk.text for chunk in chunks
    ]


def test_whole_fitting_file_keeps_its_single_chunk_fast_path():
    source = "# First policy.\nFIRST = True\n\n# Second policy.\nSECOND = False\n"
    chunks = Chunker(
        max_chunk_size=120,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    assert [chunk.text for chunk in chunks] == [source]
    _assert_source(chunks, source, 120, len)


def test_isolation_keeps_nonmonotonic_containing_window_when_prefix_would_overflow():
    source = 'one = 1\ntwo = 2\n# policy\nVALUE = 3\n\nsuffix = "' + "z" * 50 + '"\n'

    def count(text: str) -> int:
        return len(text) + (50 if "one" in text and "two" in text and "# policy" not in text else 0)

    chunks = Chunker(
        max_chunk_size=45,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 45, count)
    assert "one" in chunks[0].text and "two" in chunks[0].text and "# policy" in chunks[0].text


def test_isolated_unicode_groups_keep_complete_input_budget_and_metadata():
    prefix = 'prefix = "' + "x" * 45 + '"\r\n\r\n'
    first = "# İzin 確認 😀\r\nAPPROVED = False\r\n\r\n"
    second = "# Keep approvals attributable.\r\nAUDIT = True\r\n\r\n"
    source = prefix + first + second

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2

    chunks = Chunker(
        max_chunk_size=110,
        min_chunk_size=80,
        size_unit="tokens",
        tokenizer=count,
        context_mode="minimal",
        coverage_policy="lossless",
    ).chunk("policy.py", source)

    _assert_source(chunks, source, 110, count)
    assert [chunk.text for chunk in chunks] == [prefix, first, second]
    assert all(chunk.context.content_type.value == "code" for chunk in chunks)
    assert all(chunk.context.parse_errors == [] for chunk in chunks)
