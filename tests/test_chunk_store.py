from __future__ import annotations

import threading
from pathlib import Path

from omnichunk import Chunker
from omnichunk.serialization import stable_chunk_id
from omnichunk.store import ChunkStore


def test_chunk_store_index_and_query(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    (d / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")

    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        r = store.index(str(d), glob="**/*.py")
        assert r.files_scanned == 1
        assert r.files_updated == 1
        assert r.files_skipped == 0

        chunks = store.query(str(d / "a.py"))
        assert chunks
        assert all("def f" in c.text for c in chunks)
    finally:
        store.close()


def test_chunk_store_sync_skips_unchanged(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "x.py"
    f.write_text("x = 1\n", encoding="utf-8")

    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        r1 = store.sync(str(d), glob="**/*.py")
        assert r1.files_updated == 1
        assert r1.files_skipped == 0

        r2 = store.sync(str(d), glob="**/*.py")
        assert r2.files_updated == 0
        assert r2.files_skipped == 1
    finally:
        store.close()


def test_chunk_store_sync_updates_on_change(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "m.py"
    f.write_text("a = 1\n", encoding="utf-8")

    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        store.sync(str(d), glob="**/*.py")
        ids_v1 = {stable_chunk_id(c) for c in store.query(str(f))}

        f.write_text("a = 1\nb = 2\n", encoding="utf-8")
        r = store.sync(str(d), glob="**/*.py")
        assert r.files_updated == 1
        key = str(f.resolve())
        assert key in r.diffs
        assert r.diffs[key].removed_ids
        ids_v2 = {stable_chunk_id(c) for c in store.query(str(f))}
        assert ids_v1.isdisjoint(ids_v2)
    finally:
        store.close()


def test_chunk_store_removes_deleted_file(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "gone.py"
    f.write_text("print(1)\n", encoding="utf-8")

    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        store.sync(str(d), glob="**/*.py")
        ids_before = {stable_chunk_id(c) for c in store.query(str(f))}
        assert ids_before

        f.unlink()
        r = store.sync(str(d), glob="**/*.py")
        assert r.files_deleted >= 1
        assert set(r.removed_chunk_ids) >= ids_before
        # query path may still exist as string - file not on disk
        assert store.query(str(d / "gone.py")) == []
    finally:
        store.close()


def test_chunk_store_foreign_keys_cascade(tmp_path: Path) -> None:
    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        store._conn.execute(
            "INSERT INTO files (path, mtime_ns, size, content_sha256, last_indexed_at) "
            "VALUES (?, 0, 0, 'x', 0.0)",
            ("/tmp/fake",),
        )
        store._conn.execute(
            "INSERT INTO chunks (stable_id, filepath, chunk_json) VALUES (?, ?, ?)",
            ("sid1", "/tmp/fake", "{}"),
        )
        store._conn.execute("DELETE FROM files WHERE path = ?", ("/tmp/fake",))
        cur = store._conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE stable_id = ?",
            ("sid1",),
        )
        n = cur.fetchone()[0]
        assert n == 0
    finally:
        store.close()


def test_chunk_store_empty_glob(tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        r = store.sync(str(d), glob="**/*.py")
        assert r.files_scanned == 0
    finally:
        store.close()


def test_chunk_store_persists_across_process_restart(tmp_path: Path) -> None:
    """Close DB connection and reopen: chunks and stable IDs must match."""
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "keep.py"
    f.write_text("def keep():\n    return 42\n", encoding="utf-8")
    db = tmp_path / "store.db"

    store1 = ChunkStore(db)
    try:
        store1.sync(str(d), glob="**/*.py")
        ids_before = {stable_chunk_id(c) for c in store1.query(str(f))}
        texts_before = [c.text for c in store1.query(str(f))]
    finally:
        store1.close()

    store2 = ChunkStore(db)
    try:
        chunks = store2.query(str(f))
        assert {stable_chunk_id(c) for c in chunks} == ids_before
        assert [c.text for c in chunks] == texts_before
        assert all("return 42" in c.text for c in chunks)
    finally:
        store2.close()


def test_sync_unchanged_content_zero_diffs(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    (d / "x.py").write_text("x = 1\n", encoding="utf-8")
    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        store.sync(str(d), glob="**/*.py")
        r2 = store.sync(str(d), glob="**/*.py")
        assert r2.files_updated == 0
        assert r2.files_skipped == 1
        assert r2.diffs == {}
        assert r2.removed_chunk_ids == []
        assert r2.files_deleted == 0
    finally:
        store.close()


def test_sync_modified_only_reindexes_changed_file(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    f_a = d / "a.py"
    f_b = d / "b.py"
    f_a.write_text("a = 1\n", encoding="utf-8")
    f_b.write_text("b = 1\n", encoding="utf-8")
    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        store.sync(str(d), glob="**/*.py")
        ids_b_before = {stable_chunk_id(c) for c in store.query(str(f_b))}

        f_a.write_text("a = 1\na = 2\n", encoding="utf-8")
        r = store.sync(str(d), glob="**/*.py")
        assert r.files_updated == 1
        assert r.files_skipped == 1
        ids_b_after = {stable_chunk_id(c) for c in store.query(str(f_b))}
        assert ids_b_before == ids_b_after

        key_a = str(f_a.resolve())
        assert key_a in r.diffs
        assert r.diffs[key_a].removed_ids
    finally:
        store.close()


def test_concurrent_reads_eight_threads_same_db_file(tmp_path: Path) -> None:
    """Multiple connections read the same SQLite file (sqlite connections are not thread-safe)."""
    d = tmp_path / "proj"
    d.mkdir()
    (d / "x.py").write_text("x = 1\n" * 40, encoding="utf-8")
    db = tmp_path / "store.db"
    writer = ChunkStore(db)
    try:
        writer.sync(str(d), glob="**/*.py")
        expected_ids = {stable_chunk_id(c) for c in writer.query(str(d / "x.py"))}
        expected_texts = [c.text for c in writer.query(str(d / "x.py"))]
    finally:
        writer.close()

    errors: list[BaseException] = []
    lock = threading.Lock()

    def reader() -> None:
        try:
            local = ChunkStore(db)
            try:
                for _ in range(40):
                    chunks = local.query(str(d / "x.py"))
                    assert [c.text for c in chunks] == expected_texts
                    assert {stable_chunk_id(c) for c in chunks} == expected_ids
            finally:
                local.close()
        except BaseException as exc:
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60.0)
        assert t.is_alive() is False
    assert errors == []


def test_stream_upsert_adapter_row_shapes(tmp_path: Path) -> None:
    """Pinecone / Weaviate / Supabase row dicts from Chunker.stream_upsert."""

    def embed(texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 0.0] for t in texts]

    f = tmp_path / "doc.txt"
    f.write_text("hello 🌍 café line one\n" * 6, encoding="utf-8")
    chunker = Chunker(max_chunk_size=50, size_unit="chars", min_chunk_size=8)

    pine = list(
        chunker.stream_upsert(
            str(f), embed_fn=embed, adapter="pinecone", batch_size=2
        )
    )
    weav = list(
        chunker.stream_upsert(
            str(f), embed_fn=embed, adapter="weaviate", batch_size=2
        )
    )
    supa = list(
        chunker.stream_upsert(
            str(f), embed_fn=embed, adapter="supabase", batch_size=2
        )
    )
    assert pine and weav and supa

    for batch in pine:
        assert batch.adapter == "pinecone"
        for row in batch.rows:
            assert set(row) >= {"id", "values", "metadata"}
            assert isinstance(row["values"], list)

    for batch in weav:
        assert batch.adapter == "weaviate"
        for row in batch.rows:
            assert row.get("class") == "OmnichunkDocument"
            assert "vector" in row and "properties" in row

    for batch in supa:
        assert batch.adapter == "supabase"
        for row in batch.rows:
            assert "embedding" in row and "content" in row
            assert isinstance(row["embedding"], list)


def test_chunk_store_utf8_emoji_roundtrip(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "unicode.txt"
    payload = "café ☕ 你好\n" + "🚀" * 30 + "\nend\n"
    f.write_text(payload, encoding="utf-8")
    db = tmp_path / "store.db"
    store = ChunkStore(db)
    try:
        store.sync(str(d), glob="**/*.txt")
        combined = "".join(c.text for c in store.query(str(f)))
    finally:
        store.close()
    assert "café" in combined
    assert "☕" in combined
    assert "你好" in combined
    assert "🚀" in combined


def test_delete_sqlite_file_sync_recreates_database(tmp_path: Path) -> None:
    d = tmp_path / "proj"
    d.mkdir()
    f = d / "x.py"
    f.write_text("x = 99\n", encoding="utf-8")
    db = tmp_path / "store.db"

    s1 = ChunkStore(db)
    try:
        s1.sync(str(d), glob="**/*.py")
        assert db.is_file()
    finally:
        s1.close()

    db.unlink()
    assert not db.exists()

    s2 = ChunkStore(db)
    try:
        r = s2.sync(str(d), glob="**/*.py")
        assert db.is_file()
        assert r.files_updated == 1
        chunks = s2.query(str(f))
        assert chunks
        assert any("99" in c.text for c in chunks)
    finally:
        s2.close()
