from __future__ import annotations

import pytest

from omnichunk.util.text_index import TextIndex


def _reference_char_to_byte_and_lines(text: str) -> tuple[list[int], list[int]]:
    """Reference mapping using per-codepoint UTF-8 encode (slow but authoritative)."""
    char_to_byte: list[int] = [0] * (len(text) + 1)
    line_starts: list[int] = [0]
    byte_cursor = 0
    for idx, ch in enumerate(text):
        char_to_byte[idx] = byte_cursor
        byte_cursor += len(ch.encode("utf-8"))
        if ch == "\n":
            line_starts.append(idx + 1)
    char_to_byte[len(text)] = byte_cursor
    return char_to_byte, line_starts


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ascii only\nline two\n",
        "caf\u00e9\n",
        "euro \u20ac and newline\n",
        "CJK \u4e2d\u6587\n",
        "emoji \U0001f600 \U0001f4a9\n",
        "mixed \n \u00e9 \u0800 \U0001f680 end",
    ],
)
def test_text_index_char_to_byte_matches_encode_reference(text: str) -> None:
    ref_cb, ref_lines = _reference_char_to_byte_and_lines(text)
    idx = TextIndex(text)
    assert idx._char_to_byte == ref_cb
    assert idx._line_starts == ref_lines


@pytest.mark.parametrize("text", ["", "abc", "\n", "a\r\nb\r\nc\n", "\0\n\n", "é\r\n🚀\n"])
def test_line_and_byte_queries_match_original_text(text: str) -> None:
    idx = TextIndex(text)
    raw = text.encode("utf-8")
    for position in range(len(text) + 1):
        assert idx.byte_offset_for_char(position) == len(text[:position].encode("utf-8"))
        assert idx.line_for_char(position) == text[:position].count("\n")
    for position in range(len(raw) + 1):
        assert idx.line_for_byte(position) == raw[:position].count(b"\n")
