"""Strong clause fallback retains source units before splitting into words."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from omnichunk import Chunker
from omnichunk.types import Chunk


def _assert_source(chunks: list[Chunk], source: str, capacity: int, count: Callable[[str], int]):
    assert "".join(chunk.text for chunk in chunks) == source
    raw = source.encode("utf-8")
    cursor = 0
    for chunk in chunks:
        assert chunk.byte_range.start == cursor
        cursor = chunk.byte_range.end
        assert raw[chunk.byte_range.start : cursor].decode("utf-8") == chunk.text
        assert count(chunk.contextualized_text) <= capacity
    assert cursor == len(raw)


@pytest.mark.parametrize("filepath", ["notes.txt", "notes.md"])
@pytest.mark.parametrize("separator", [";", "；", ";；"])
def test_oversized_sentence_keeps_fitting_semicolon_clauses_whole(filepath, separator):
    first = "The owner records the publication decision" + separator
    second = " the reviewer preserves all source references."
    source = first + second
    chunker = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk(filepath, source)

    _assert_source(chunks, source, 64, len)
    assert [chunk.text for chunk in chunks] == [first, second]
    assert [chunk.text for chunk in chunker.stream(filepath, source)] == [first, second]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_unicode_clause_boundaries_preserve_complete_input_token_budgets(newline):
    clauses = ["公開前に記録を確認；", "担当者は理由を保存；", "監査者は参照を保持。" + newline]
    source = "".join(clauses)

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2

    chunks = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    _assert_source(chunks, source, 64, count)
    assert all(any(clause in chunk.text for chunk in chunks) for clause in clauses)
    assert len(chunks) >= 2


def test_clause_packing_checks_nonadditive_whole_payload_cost():
    first = "The owner records the publication decision;"
    second = " the reviewer preserves all source references."
    source = first + second

    def count(text: str) -> int:
        return len(text) + 2 + (40 if "decision" in text and "reviewer" in text else 0)

    chunks = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    _assert_source(chunks, source, 64, count)
    assert [chunk.text for chunk in chunks] == [first, second]


def test_complete_fitting_semicolon_sentence_stays_a_single_payload():
    source = "Keep source citations; preserve approval reasons."
    chunks = Chunker(
        max_chunk_size=64,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    _assert_source(chunks, source, 64, len)
    assert [chunk.text for chunk in chunks] == [source]
