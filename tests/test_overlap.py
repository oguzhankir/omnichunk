from __future__ import annotations

from omnichunk import Chunker


def test_line_overlap_contextualized_text() -> None:
    code = "def a():\n    return 1\n\ndef b():\n    return 2\n\ndef c():\n    return 3\n"
    chunker = Chunker(max_chunk_size=28, min_chunk_size=8, size_unit="chars", overlap_lines=1)

    chunks = chunker.chunk("example.py", code)

    assert len(chunks) >= 2
    assert any("# ..." in c.contextualized_text for c in chunks[1:])


def test_token_overlap_produces_chunks() -> None:
    code = "\n".join(f"def fn_{i}():\n    return {i}\n" for i in range(12))
    chunker = Chunker(max_chunk_size=80, min_chunk_size=20, size_unit="chars", overlap=0.2)

    chunks = chunker.chunk("many.py", code)

    assert chunks
    assert all(c.total_chunks == len(chunks) for c in chunks)
