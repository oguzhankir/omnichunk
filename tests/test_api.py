from __future__ import annotations

import json
from pathlib import Path

from omnichunk import Chunker, chunk, chunk_directory, chunk_file


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


def test_chunk_directory_glob_and_hidden_filters(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (src_dir / "b.md").write_text("# title\n", encoding="utf-8")

    nested = src_dir / "nested"
    nested.mkdir()
    (nested / "c.py").write_text("def c():\n    return 3\n", encoding="utf-8")
    (nested / ".hidden.py").write_text("def hidden():\n    return 0\n", encoding="utf-8")

    results = chunk_directory(
        str(src_dir),
        glob="**/*.py",
        max_chunk_size=40,
        size_unit="chars",
    )

    filepaths = [Path(item.filepath).name for item in results]
    assert filepaths == ["a.py", "c.py"]
    assert all(item.error is None for item in results)
    assert all(item.chunks for item in results)


def test_chunker_export_and_quality_helpers() -> None:
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    chunker = Chunker(max_chunk_size=48, min_chunk_size=12, size_unit="chars")
    chunks = chunker.chunk("calc.py", code)

    payload = chunker.to_dicts(chunks)
    assert payload
    assert payload[0]["context"]["filepath"] == "calc.py"

    jsonl = chunker.to_jsonl(chunks)
    lines = [line for line in jsonl.splitlines() if line.strip()]
    assert lines
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]["context"]["filepath"] == "calc.py"

    csv_payload = chunker.to_csv(chunks)
    assert "filepath" in csv_payload.splitlines()[0]
    assert "calc.py" in csv_payload

    stats = chunker.chunk_stats(chunks, size_unit="chars")
    assert stats.total_chunks == len(chunks)
    assert stats.average_size > 0

    quality = chunker.quality_scores(
        chunks,
        min_chunk_size=12,
        max_chunk_size=48,
        size_unit="chars",
    )
    assert quality
    assert all(0.0 <= item.overall <= 1.0 for item in quality)


def test_chunker_with_python_nws_backend_keeps_integrity() -> None:
    content = (
        "def a(x: int) -> int:\n"
        "    return x + 1\n\n\n"
        "def b(y: int) -> int:\n"
        "    return y + 2\n"
    )
    chunker = Chunker(
        max_chunk_size=42,
        min_chunk_size=10,
        size_unit="chars",
        nws_backend="python",
    )

    chunks = chunker.chunk("module.py", content)
    assert chunks
    assert "".join(chunk.text for chunk in chunks) == content
    for left, right in zip(chunks, chunks[1:]):
        assert left.byte_range.end == right.byte_range.start
