from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker, chunk, chunk_file


def test_chunk_function_simple_python() -> None:
    code = "def foo(x):\n    return x + 1\n"
    chunks = chunk("example.py", code, max_chunk_size=32, size_unit="chars")

    assert chunks
    assert all(c.text for c in chunks)
    assert chunks[0].context.filepath == "example.py"


def test_chunker_stream_sets_unknown_total() -> None:
    text = "# Title\n\nHello world\n\nSecond paragraph."
    chunker = Chunker(max_chunk_size=20, size_unit="chars")

    streamed = list(chunker.stream("doc.md", text))
    assert streamed
    assert all(c.total_chunks == -1 for c in streamed)


def test_stream_text_matches_chunk_output_across_engines() -> None:
    chunker = Chunker(max_chunk_size=40, min_chunk_size=8, size_unit="chars")
    cases = [
        ("sample.py", "def add(a, b):\n    return a + b\n"),
        ("doc.md", "# Title\n\nParagraph one.\n\nParagraph two."),
        ("data.json", '{"a": 1, "b": {"c": 2}}'),
        (
            "cells.py",
            '# %% [markdown]\n"""\n# Intro\n"""\n# %%\nprint(\'hi\')\n',
        ),
    ]

    for filepath, content in cases:
        chunked = chunker.chunk(filepath, content)
        streamed = list(chunker.stream(filepath, content))

        assert [c.text for c in streamed] == [c.text for c in chunked]
        assert all(c.total_chunks == -1 for c in streamed)


def test_chunk_file_reads_disk(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.py"
    file_path.write_text("def ping():\n    return 'pong'\n", encoding="utf-8")

    chunks = chunk_file(str(file_path), max_chunk_size=40, size_unit="chars")
    assert chunks
    assert "ping" in "\n".join(c.text for c in chunks)


def test_batch_keeps_input_order() -> None:
    chunker = Chunker(max_chunk_size=30, size_unit="chars")
    files = [
        {"filepath": "a.py", "code": "def a():\n    return 1\n"},
        {"filepath": "b.md", "code": "# B\n\nText"},
        {"filepath": "c.json", "code": '{"k": 1, "v": 2}'},
    ]

    results = chunker.batch(files, concurrency=2)

    assert [r.filepath for r in results] == ["a.py", "b.md", "c.json"]
    assert all(r.error is None for r in results)
    assert all(r.chunks for r in results)
