"""
Streaming and async: stream(), achunk(), astream(), abatch() with asyncio.run().
"""

from __future__ import annotations

import asyncio

from omnichunk import Chunker


def main() -> None:
    src = "def f(n):\n    return n + 1\n" * 8
    chunker = Chunker(max_chunk_size=48, size_unit="chars")

    n_stream = 0
    raw = src.encode("utf-8")
    for c in chunker.stream("loop.py", src):
        n_stream += 1
        assert c.total_chunks == -1
        assert raw[c.byte_range.start : c.byte_range.end].decode("utf-8") == c.text
    print(f"stream() yielded: {n_stream} chunks (total_chunks=-1 on each)")

    async def run_async() -> None:
        ach = await chunker.achunk("a.py", src)
        print(f"achunk count: {len(ach)}")

        n_ast = 0
        async for c in chunker.astream("a.py", src):
            n_ast += 1
        print(f"astream yielded: {n_ast}")

        batch = await chunker.abatch(
            [
                {"filepath": "x.py", "code": "def a():\n    pass\n"},
                {"filepath": "y.py", "code": "def b():\n    pass\n"},
            ],
            concurrency=2,
        )
        print(f"abatch results: {len(batch)}")
        for br in batch:
            print(f"  {br.filepath}: {len(br.chunks)} chunks err={br.error!r}")

    asyncio.run(run_async())


if __name__ == "__main__":
    main()
