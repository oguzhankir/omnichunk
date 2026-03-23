from __future__ import annotations

from pathlib import Path

from omnichunk import Chunker


def _embed(texts: list[str]) -> list[list[float]]:
    return [[float(len(t)), 0.0] for t in texts]


def test_stream_upsert_single_file_batches(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("def x():\n    return 1\n" * 20, encoding="utf-8")
    chunker = Chunker(max_chunk_size=80, size_unit="chars", min_chunk_size=10)
    batches = list(
        chunker.stream_upsert(
            str(f),
            embed_fn=_embed,
            adapter="pinecone",
            batch_size=2,
        )
    )
    assert batches
    assert all(b.adapter == "pinecone" for b in batches)
    assert all("id" in r for b in batches for r in b.rows)
    total_rows = sum(len(b.rows) for b in batches)
    total_chunks = sum(len(b.chunks) for b in batches)
    assert total_rows == total_chunks


def test_stream_upsert_directory_adapters(tmp_path: Path) -> None:
    d = tmp_path / "src"
    d.mkdir()
    (d / "a.py").write_text("x = 1\n", encoding="utf-8")
    (d / "b.py").write_text("y = 2\n", encoding="utf-8")
    chunker = Chunker(max_chunk_size=500, size_unit="chars")
    pine = list(
        chunker.stream_upsert(str(d), glob="**/*.py", embed_fn=_embed, adapter="pinecone")
    )
    weav = list(
        chunker.stream_upsert(str(d), glob="**/*.py", embed_fn=_embed, adapter="weaviate")
    )
    supa = list(
        chunker.stream_upsert(str(d), glob="**/*.py", embed_fn=_embed, adapter="supabase")
    )
    assert pine[0].rows[0].get("class") is None
    assert weav[0].rows[0].get("class") == "OmnichunkDocument"
    assert "embedding" in supa[0].rows[0]


def test_stream_upsert_embed_len_mismatch_raises(tmp_path: Path) -> None:
    f = tmp_path / "x.py"
    f.write_text("def x():\n    return 1\n" * 20, encoding="utf-8")
    chunker = Chunker(max_chunk_size=80, size_unit="chars", min_chunk_size=10)

    def bad_embed(_texts: list[str]) -> list[list[float]]:
        return [[0.0]]

    try:
        list(chunker.stream_upsert(str(f), embed_fn=bad_embed, batch_size=2))
    except ValueError as e:
        assert "embed_fn" in str(e).lower() or "vectors" in str(e).lower()
    else:
        raise AssertionError("expected ValueError")
