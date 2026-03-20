"""
Quickstart: one-shot chunk(), reusable Chunker, inspecting Chunk fields,
temp file + chunk_file(), and batch() over multiple in-memory files.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from omnichunk import Chunker, chunk


def main() -> None:
    source = '''\
import os

def greet(name: str) -> str:
    """Say hello."""
    return f"hello {name}"
'''

    # One-shot API (kwargs map to ChunkOptions)
    chunks_once = chunk("example.py", source, max_chunk_size=256, size_unit="chars")
    print(f"one-shot chunk count: {len(chunks_once)}")

    # Reusable Chunker with defaults
    chunker = Chunker(max_chunk_size=256, size_unit="chars", context_mode="full")
    chunks = chunker.chunk("example.py", source)
    print(f"Chunker chunk count: {len(chunks)}")
    if chunks:
        c0 = chunks[0]
        print("--- first chunk ---")
        print("text (first 120 chars):", repr(c0.text[:120]))
        print("byte_range:", c0.byte_range)
        print("line_range:", c0.line_range)
        print("breadcrumb:", c0.context.breadcrumb)
        print("contextualized_text (first 120 chars):", repr(c0.contextualized_text[:120]))
        print("token_count:", c0.token_count, "char_count:", c0.char_count, "nws_count:", c0.nws_count)

    # chunk_file() via tempfile (no repo paths)
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "sample.py"
        p.write_text(source, encoding="utf-8")
        from_disk = chunker.chunk_file(str(p))
        print(f"chunk_file count: {len(from_disk)}")

    # batch(): list of dicts with filepath + code
    batch_in = [
        {"filepath": "a.py", "code": "def a():\n    return 1\n"},
        {"filepath": "b.py", "code": "def b():\n    return 2\n"},
    ]
    results = chunker.batch(batch_in, concurrency=2)
    print(f"batch files: {len(results)}")
    for br in results:
        print(f"  {br.filepath}: {len(br.chunks)} chunks")


if __name__ == "__main__":
    main()
