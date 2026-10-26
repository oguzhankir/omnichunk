"""Bracket structure guards only prose fallback sentence boundaries."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from omnichunk import Chunker
from omnichunk.engine.prose_engine import _prose_sentence_ends
from omnichunk.semantic.sentences import split_sentences
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
@pytest.mark.parametrize(
    "reference", ["[guide. 384 records changes]", "[outer [guide. 384] notes]"]
)
def test_fitting_bracket_reference_stays_with_its_complete_sentence(filepath, reference):
    before = "The operator signs the checklist. "
    citation = f"Read {reference} before approval. "
    after = "Keep every source reference intact."
    source = before + citation + after
    chunker = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    )
    chunks = chunker.chunk(filepath, source)

    _assert_source(chunks, source, 64, len)
    assert any(citation in chunk.text for chunk in chunks)
    assert [chunk.text for chunk in chunker.stream(filepath, source)] == [
        chunk.text for chunk in chunks
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_multilingual_bracket_expression_keeps_exact_native_style_input_ranges(newline):
    before = "記録を保存する。"
    citation = "[案内. 第三章は変更理由を示す]を参照する。"
    source = before + citation + "担当者に通知する。" + newline

    def count(text: str) -> int:
        return len(text.encode("utf-8")) + 2

    chunks = Chunker(
        max_chunk_size=96,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    _assert_source(chunks, source, 96, count)
    assert any(citation in chunk.text for chunk in chunks)


@pytest.mark.parametrize(
    "text",
    [
        r"Read \[guide. 384 remains literal\]. Continue afterward.",
        r"Read [guide. 384\] remains unfinished. Continue afterward.",
        "Read [guide. 384 remains unfinished. Continue afterward.",
    ],
)
def test_escaped_or_unmatched_brackets_do_not_hide_later_sentence_boundaries(text):
    ends = _prose_sentence_ends(text)

    assert text.index("384") in ends
    assert text.index("Continue") in ends


def test_balanced_inner_reference_survives_an_unmatched_outer_bracket():
    text = "Read [unfinished [guide. 384] notes. Continue afterward. Finish."
    ends = _prose_sentence_ends(text)

    assert text.index("384") not in ends
    assert text.index("Continue") in ends
    assert text.index("Finish") in ends


def test_even_backslashes_leave_a_bracket_pair_active():
    text = r"Read \\[guide. 384 records changes]. Continue afterward."
    ends = _prose_sentence_ends(text)

    assert text.index("384") not in ends
    assert text.index("Continue") in ends


def test_closing_bracket_ends_a_sentence_without_changing_the_semantic_splitter():
    text = "Read [guide. 384 records changes.] Continue afterward."
    original = split_sentences(text)

    assert text.index("384") in [end for _, _, end in original]
    assert text.index("384") not in _prose_sentence_ends(text)
    assert text.index("Continue") in _prose_sentence_ends(text)
    assert split_sentences(text) == original


def test_bracket_boundary_guard_keeps_nonadditive_complete_payload_budgets():
    before = "The operator signs the checklist. "
    citation = "Read [guide. 384 records changes] before approval. "
    source = before + citation + "Keep every source reference intact."

    def count(text: str) -> int:
        return len(text) + 2 + (8 if "signs" in text and "[guide" in text else 0)

    chunks = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    _assert_source(chunks, source, 64, count)
    assert any(citation in chunk.text for chunk in chunks)


def test_oversized_bracket_expression_still_uses_normal_word_fallback():
    source = "Read [guide. 384 " + "source references " * 12 + "] before approval."
    chunks = Chunker(
        max_chunk_size=64,
        min_chunk_size=0,
        size_unit="chars",
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("notes.txt", source)

    _assert_source(chunks, source, 64, len)
    assert len(chunks) > 1
