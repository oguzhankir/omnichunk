from __future__ import annotations

import asyncio

from omnichunk import Chunker

CODE = "def foo():\n    return 1\n" * 20


def test_achunk_returns_same_as_chunk() -> None:
    chunker = Chunker(max_chunk_size=128, size_unit="chars")
    sync_result = chunker.chunk("test.py", CODE)
    async_result = asyncio.run(chunker.achunk("test.py", CODE))
    assert len(sync_result) == len(async_result)
    assert [c.text for c in sync_result] == [c.text for c in async_result]


def test_astream_reconstruction() -> None:
    chunker = Chunker(max_chunk_size=128, size_unit="chars")

    async def _run() -> list:
        chunks = []
        async for ch in chunker.astream("test.py", CODE):
            chunks.append(ch)
        return chunks

    chunks = asyncio.run(_run())
    assert "".join(c.text for c in chunks) == CODE


def test_abatch_processes_all() -> None:
    chunker = Chunker(max_chunk_size=128, size_unit="chars")
    inputs = [{"filepath": f"f{i}.py", "code": CODE} for i in range(5)]
    results = asyncio.run(chunker.abatch(inputs, concurrency=3))
    assert len(results) == 5
    assert all(r.error is None for r in results)


def test_abatch_handles_empty_item() -> None:
    chunker = Chunker(max_chunk_size=128, size_unit="chars")
    inputs = [{"filepath": "", "code": ""}]
    results = asyncio.run(chunker.abatch(inputs))
    assert len(results) == 1
