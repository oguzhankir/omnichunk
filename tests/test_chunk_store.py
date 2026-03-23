from __future__ import annotations

from pathlib import Path

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
