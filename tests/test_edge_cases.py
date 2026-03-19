from __future__ import annotations

from omnichunk import Chunker


def test_empty_input_returns_empty_list() -> None:
    chunker = Chunker()
    assert chunker.chunk("empty.py", "") == []
    assert chunker.chunk("spaces.txt", "   \n\n\t") == []


def test_unicode_integrity() -> None:
    text = "# Başlık 😀\n\nMerhaba dünya. 你好世界. مرحبا بالعالم."
    chunker = Chunker(max_chunk_size=30, min_chunk_size=5, size_unit="chars")

    chunks = chunker.chunk("unicode.md", text)

    assert chunks
    assert "".join(c.text for c in chunks) == text


def test_no_whitespace_only_chunks() -> None:
    code = "def a():\n    return 1\n\n\n\n\ndef b():\n    return 2\n"
    chunker = Chunker(max_chunk_size=30, min_chunk_size=5, size_unit="chars")

    chunks = chunker.chunk("x.py", code)

    assert chunks
    assert all(c.text.strip() for c in chunks)


def test_contiguous_byte_ranges() -> None:
    code = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    chunker = Chunker(max_chunk_size=22, min_chunk_size=5, size_unit="chars")

    chunks = chunker.chunk("x.py", code)

    assert chunks
    for left, right in zip(chunks, chunks[1:], strict=False):
        assert left.byte_range.end == right.byte_range.start
