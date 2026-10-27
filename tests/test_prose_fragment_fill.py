"""Experimental prose partitioning trades sentence isolation for fewer fragments."""

from __future__ import annotations

import pytest

from omnichunk import Chunker


@pytest.mark.parametrize("ending", ["\n", "\r\n"])
def test_underfilled_sentence_windows_can_use_fewer_word_windows(ending):
    source = "A sentence about cats. A sentence about dogs. A sentence about birds." + ending
    chunker = Chunker(
        max_chunk_size=40,
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
        prose_boundary_policy="compact",
    )
    chunks = chunker.chunk("notes.txt", source)
    assert len(chunks) == 2
    assert "".join(c.text for c in chunks) == source
    assert all(len(c.contextualized_text) <= 40 for c in chunks)
    assert [c.text for c in chunker.stream("notes.txt", source)] == [c.text for c in chunks]


def test_fill_keeps_complete_nonadditive_budget():
    source = "A sentence about İ cats. A sentence about 😀 dogs. A sentence about birds."

    def count(text):
        return len(text.encode()) + (10 if "😀" in text else 0)

    chunks = Chunker(
        max_chunk_size=50,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
        prose_boundary_policy="compact",
    ).chunk("notes.txt", source)
    assert "".join(c.text for c in chunks) == source
    for c in chunks:
        assert count(c.text) <= 50
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text


def test_default_keeps_fitting_sentences_and_override_is_local():
    source = "A sentence about cats. A sentence about dogs. A sentence about birds."
    chunker = Chunker(max_chunk_size=40, min_chunk_size=0, context_mode="none")
    normal = chunker.chunk("notes.txt", source)
    compact = chunker.chunk("notes.txt", source, prose_boundary_policy="compact")
    assert len(normal) == 3 and len(compact) == 2
    assert normal[0].config_fingerprint != compact[0].config_fingerprint
    assert [c.text for c in chunker.chunk("notes.txt", source)] == [c.text for c in normal]
    with pytest.raises(ValueError, match="prose_boundary_policy"):
        Chunker(prose_boundary_policy="invalid")


def test_compact_does_not_override_preserve_overflow_policy():
    source = "A sentence about cats. A sentence about dogs. A sentence about birds."
    chunks = Chunker(
        max_chunk_size=40,
        min_chunk_size=0,
        context_mode="none",
        prose_boundary_policy="compact",
        overflow_policy="preserve",
    ).chunk("notes.txt", source)
    assert [c.text for c in chunks] == [source]
