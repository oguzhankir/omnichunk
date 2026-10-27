"""Oversized documented statements retain a fitting explanatory comment tail."""

from __future__ import annotations

import pytest

from omnichunk import Chunker


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("punctuation", [". ", "。"])
def test_comment_tail_stays_with_statement(newline, punctuation):
    lead = "# This sentence gives background" + punctuation
    tail = "This sentence explains the setting" + punctuation.rstrip() + newline
    statement = "ENABLED = False" + newline
    source = lead + tail + statement
    limit = len(tail + statement) + 2
    chunker = Chunker(
        max_chunk_size=limit, min_chunk_size=0, context_mode="none", coverage_policy="lossless"
    )
    chunks = chunker.chunk("settings.py", source)
    assert [c.text for c in chunks] == [lead, tail + statement]
    assert [c.text for c in chunker.stream("settings.py", source)] == [c.text for c in chunks]
    assert b"".join(c.text.encode() for c in chunks) == source.encode()
    for c in chunks:
        assert len(c.text) <= limit
        assert source.encode()[c.byte_range.start : c.byte_range.end].decode() == c.text


def test_complete_tail_budget_includes_inline_comments():
    lead = "# This sentence gives background. "
    tail = "This sentence explains the setting.\n"
    statement = "ENABLED = False  # audited\n"
    source = lead + tail + statement
    chunks = Chunker(
        max_chunk_size=len(tail + statement),
        min_chunk_size=0,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("settings.py", source)
    assert [c.text for c in chunks] == [lead, tail + statement]


def test_nonadditive_counter_rejects_overflowing_rebalanced_tail():
    source = "# Background information. This explains behavior.\nENABLED = False\n"

    def count(text):
        return len(text) + (100 if text.startswith("This") and "ENABLED" in text else 0)

    chunks = Chunker(
        max_chunk_size=55,
        min_chunk_size=0,
        size_unit="tokens",
        tokenizer=count,
        context_mode="none",
        coverage_policy="lossless",
    ).chunk("settings.py", source)
    assert "".join(c.text for c in chunks) == source
    assert all(count(c.text) <= 55 for c in chunks)
    assert not any(c.text.startswith("This") and "ENABLED" in c.text for c in chunks)


@pytest.mark.parametrize(
    ("path", "leading", "tail", "statement"),
    [
        (
            "settings.js",
            "// Background information. ",
            "This explains the setting.\n",
            "const enabled = false;\n",
        ),
        (
            "settings.c",
            "/* Background information. ",
            "This explains the setting. */\n",
            "int enabled = 0;\n",
        ),
    ],
)
def test_comment_sentence_rebalance_in_other_ast_languages(path, leading, tail, statement):
    source = leading + tail + statement
    limit = len(tail + statement) + 1
    chunks = Chunker(
        max_chunk_size=limit, min_chunk_size=0, context_mode="none", coverage_policy="lossless"
    ).chunk(path, source)
    assert [c.text for c in chunks] == [leading, tail + statement]
