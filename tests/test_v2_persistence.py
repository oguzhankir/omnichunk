from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from omnichunk import Chunker
from omnichunk import serialization as serialization_module
from omnichunk.diff import diff_chunks
from omnichunk.plugins import PluginRegistry
from omnichunk.serialization import (
    chunk_content_fingerprint,
    chunk_embedding_fingerprint,
    chunk_from_dict,
    chunk_to_dict,
    chunks_to_csv,
    chunks_to_langchain_docs,
    chunks_to_llamaindex_docs,
    chunks_to_supabase_rows,
    chunks_to_weaviate_objects,
    stable_chunk_id,
)
from omnichunk.store import ChunkStore, LegacyStoreError, migrate_legacy_store
from omnichunk.types import (
    ByteRange,
    Chunk,
    ChunkContext,
    ContentType,
    EntityInfo,
    EntityType,
    ImportInfo,
    LineRange,
    SiblingInfo,
    SourceDescriptor,
)


def rich_chunk() -> Chunk:
    entity = EntityInfo(
        "f", EntityType.FUNCTION, "def f()", "doc", ByteRange(0, 5), LineRange(0, 1)
    )
    return Chunk(
        "café",
        "# scope\ncafé",
        ByteRange(0, 5),
        LineRange(0, 0),
        0,
        1,
        ChunkContext(
            filepath="f.py",
            language="python",
            content_type=ContentType.CODE,
            scope=[entity],
            breadcrumb=["Module", "f"],
            entities=[entity],
            siblings=[SiblingInfo("g", EntityType.FUNCTION, "after", 1, "def g()")],
            imports=[ImportInfo("os", "os", is_namespace=True)],
            heading_hierarchy=["Title"],
            section_type="code",
            parse_errors=["fallback"],
            format_metadata={"page": 2, "nested": {"items": [1, True, None]}},
        ),
        token_count=2,
        char_count=4,
        nws_count=4,
    )


def test_complete_context_survives_json_roundtrip() -> None:
    original = rich_chunk()
    assert chunk_from_dict(json.loads(json.dumps(chunk_to_dict(original)))) == original


def test_same_length_edit_invalidates_diff() -> None:
    chunker = Chunker(size_unit="chars", context_mode="none")
    previous = chunker.chunk("a.py", "a = 1\n")
    result = chunker.chunk_diff("a.py", "a = 2\n", previous_chunks=previous)
    assert result.added
    assert result.removed_ids == [stable_chunk_id(previous[0])]
    assert not result.unchanged


def test_single_file_sync_preserves_cached_siblings(tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("a = 1\n")
    b.write_text("b = 1\n")
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(tmp_path, glob="**/*.py", size_unit="chars")
        before = store.query(str(b))
        result = store.sync(a, size_unit="chars")
        assert result.files_deleted == 0
        assert store.query(str(b)) == before


def test_sync_preserves_another_root(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "x.py").write_text("a = 1\n")
    (b / "x.py").write_text("b = 1\n")
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(a, size_unit="chars")
        store.sync(b, size_unit="chars")
        assert store.query(str(a / "x.py"))


def test_config_change_reindexes_unchanged_file(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("line content\n" * 12)
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(source, size_unit="chars", max_chunk_size=100, min_chunk_size=1)
        result = store.sync(source, size_unit="chars", max_chunk_size=30, min_chunk_size=1)
        assert result.files_updated == 1
        assert result.files_skipped == 0


def test_provider_failure_rolls_back_and_can_retry(tmp_path: Path) -> None:
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("a = 1\n")
    b.write_text("b = 1\n")

    class FailingChunker(Chunker):
        def chunk_file(
            self, path: str, *, encoding: str = "utf-8", **options: object
        ) -> list[Chunk]:
            if path.endswith("b.py"):
                raise RuntimeError("provider unavailable")
            return super().chunk_file(path, encoding=encoding, **options)

    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(tmp_path, glob="**/*.py", size_unit="chars")
        old_a, old_b = store.query(str(a)), store.query(str(b))
        a.write_text("a = 2\n")
        b.write_text("b = 2\n")
        with pytest.raises(RuntimeError, match="provider unavailable"):
            store.sync(tmp_path, glob="**/*.py", chunker=FailingChunker(size_unit="chars"))
        assert store.query(str(a)) == old_a
        assert store.query(str(b)) == old_b
        result = store.sync(tmp_path, glob="**/*.py", size_unit="chars")
        assert result.files_updated == 2


def test_query_returns_source_order(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("".join(f"unique line {i}\n" for i in range(20)))
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(source, size_unit="chars", max_chunk_size=30, min_chunk_size=1)
        chunks = store.query(str(source))
        assert len(chunks) > 2
        assert [c.index for c in chunks] == sorted(c.index for c in chunks)


def test_unknown_serialization_version_rejected() -> None:
    payload = chunk_to_dict(rich_chunk())
    payload["schema_version"] = 999
    with pytest.raises(ValueError, match="schema"):
        chunk_from_dict(payload)


def test_legacy_unversioned_context_reader() -> None:
    chunk = rich_chunk()
    payload = chunk_to_dict(chunk)
    payload.pop("schema_version", None)
    assert chunk_from_dict(payload) == chunk


def test_v2_source_and_diagnostics_roundtrip() -> None:
    original = replace(
        rich_chunk(),
        occurrence=3,
        config_fingerprint="configuration-v2",
        source=SourceDescriptor(
            "document-1",
            "revision-2",
            format_name="pdf",
            normalization="extracted",
            metadata={"pages": [1, 2]},
        ),
        metadata={"budget": {"limit": 40, "overflow": False}, "warnings": ["extracted"]},
    )
    payload = json.loads(json.dumps(chunk_to_dict(original)))
    assert payload["schema_version"] == 2
    assert chunk_from_dict(payload) == original


def test_moved_chunk_identity_is_separate_from_source_revision() -> None:
    old = replace(rich_chunk(), source=SourceDescriptor("logical-document", "old"))
    moved = replace(
        old,
        source=SourceDescriptor("logical-document", "new"),
        index=5,
        byte_range=ByteRange(50, 55),
        line_range=LineRange(4, 4),
    )
    assert stable_chunk_id(old) == stable_chunk_id(moved)
    assert chunk_content_fingerprint(old) == chunk_content_fingerprint(moved)
    assert chunk_embedding_fingerprint(old) == chunk_embedding_fingerprint(moved)
    result = diff_chunks([old], [moved])
    assert result.unchanged == [moved]
    assert not result.added and not result.removed_ids


@pytest.mark.parametrize("change", ["rendered", "config"])
def test_same_identity_payload_change_updates_legacy_consumers(change: str) -> None:
    old = replace(rich_chunk(), source=SourceDescriptor("doc", "r1"))
    new = (
        replace(old, contextualized_text="new imports\ncafé")
        if change == "rendered"
        else replace(old, config_fingerprint="new-config")
    )
    assert stable_chunk_id(old) == stable_chunk_id(new)
    result = diff_chunks([old], [new])
    assert result.updated == result.added == [new]
    assert result.removed_ids == [stable_chunk_id(old)]
    assert not result.unchanged


def test_equal_chunks_use_occurrences_and_reject_collisions() -> None:
    first = replace(rich_chunk(), source=SourceDescriptor("doc", "r"), occurrence=0)
    second = replace(first, occurrence=1, index=1)
    assert stable_chunk_id(first) != stable_chunk_id(second)
    result = diff_chunks([first, second], [first])
    assert result.removed_ids == [stable_chunk_id(second)]
    with pytest.raises(ValueError, match="duplicate occurrence"):
        diff_chunks([first, first], [first])
    with pytest.raises(ValueError, match="duplicate occurrence"):
        diff_chunks([first], [first, first])


def test_rename_requires_retained_logical_source_id() -> None:
    old = replace(rich_chunk(), source=SourceDescriptor("logical-id", "r1"))
    new = replace(old, context=replace(old.context, filepath="renamed.py"))
    assert stable_chunk_id(old) == stable_chunk_id(new)
    changed_source = replace(new, source=SourceDescriptor("different-id", "r1"))
    assert stable_chunk_id(old) != stable_chunk_id(changed_source)
    assert stable_chunk_id(old, filepath="explicit-override") != stable_chunk_id(old)


def test_collection_and_filter_scopes_are_independent(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    text = tmp_path / "b.txt"
    source.write_text("a = 1\n")
    text.write_text("text\n")
    db = tmp_path / "store.db"
    with ChunkStore(db, collection="a") as first, ChunkStore(db, collection="b") as second:
        first.sync(tmp_path, glob="**/*", size_unit="chars")
        second.sync(source, size_unit="chars", context_mode="none")
        first_text = first.query(str(text))
        other_collection = second.query(str(source))
        assert first_text and other_collection
        assert second.query(str(text)) == []
        first.sync(tmp_path, glob="**/*.py", size_unit="chars")
        assert first.query(str(text)) == first_text
        source.unlink()
        first.sync(tmp_path, glob="**/*.py", size_unit="chars")
        assert first.query(str(source)) == []
        assert second.query(str(source)) == other_collection


def test_sql_failure_rolls_back_and_retry_succeeds(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("first\n")
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(source, size_unit="chars")
        previous = store.query(str(source))
        source.write_text("second\n")
        store._conn.execute(
            "CREATE TRIGGER fail_insert BEFORE INSERT ON chunks "
            "BEGIN SELECT RAISE(ABORT, 'forced failure'); END"
        )
        with pytest.raises(sqlite3.IntegrityError, match="forced failure"):
            store.sync(source, size_unit="chars")
        assert store.query(str(source)) == previous
        store._conn.execute("DROP TRIGGER fail_insert")
        assert store.sync(source, size_unit="chars").files_updated == 1
        assert "".join(c.text for c in store.query(str(source))) == "second\n"


def test_source_changed_during_chunking_rolls_back(tmp_path: Path) -> None:
    source = tmp_path / "a.txt"
    source.write_text("before\n")

    class MutatingChunker(Chunker):
        def chunk_file(
            self, path: str, *, encoding: str = "utf-8", **options: object
        ) -> list[Chunk]:
            result = super().chunk_file(path, encoding=encoding, **options)
            Path(path).write_text("mutated\n")
            return result

    with ChunkStore(tmp_path / "store.db") as store:
        with pytest.raises(RuntimeError, match="Source changed"):
            store.sync(source, chunker=MutatingChunker(size_unit="chars"))
        assert store.query(str(source)) == []
        assert store.sync(source, size_unit="chars").files_updated == 1


def test_escaping_source_symlink_does_not_delete_cached_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    inside, outside = root / "inside.txt", tmp_path / "outside.txt"
    inside.write_text("inside\n")
    outside.write_text("outside\n")
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(root, size_unit="chars")
        before = store.query(str(inside))
        (root / "escape.txt").symlink_to(outside)
        with pytest.raises(ValueError, match="escapes indexing root"):
            store.sync(root, size_unit="chars")
        assert store.query(str(inside)) == before


def create_legacy_database(db: Path, chunk: Chunk, *, malformed: bool = False) -> None:
    payload = chunk_to_dict(chunk)
    payload.pop("schema_version")
    payload.pop("source", None)
    payload.pop("occurrence", None)
    payload.pop("config_fingerprint", None)
    payload.pop("metadata", None)
    with sqlite3.connect(db) as conn:
        conn.executescript(
            "CREATE TABLE files (path TEXT PRIMARY KEY, mtime_ns INTEGER, size INTEGER, "
            "content_sha256 TEXT, last_indexed_at REAL);"
            "CREATE TABLE chunks (stable_id TEXT PRIMARY KEY, filepath TEXT, chunk_json TEXT);"
        )
        conn.execute(
            "INSERT INTO files VALUES (?, 0, 5, 'old-revision', 0)", (chunk.context.filepath,)
        )
        conn.execute(
            "INSERT INTO chunks VALUES ('old-id', ?, ?)",
            (chunk.context.filepath, "{" if malformed else json.dumps(payload)),
        )


def test_legacy_store_requires_explicit_copy_and_preserves_source(tmp_path: Path) -> None:
    db, converted = tmp_path / "legacy.db", tmp_path / "v2.db"
    original = replace(
        rich_chunk(), context=replace(rich_chunk().context, filepath=str(tmp_path / "f.py"))
    )
    create_legacy_database(db, original)
    before = db.read_bytes()
    with pytest.raises(LegacyStoreError, match="separate destination"):
        ChunkStore(db)
    assert db.read_bytes() == before
    result = migrate_legacy_store(db, converted)
    assert result.files_copied == result.chunks_copied == 1
    assert result.reindex_required
    assert db.read_bytes() == before
    with ChunkStore(converted) as store:
        chunks = store.query(original.context.filepath)
        assert chunks[0].context == original.context
        assert chunks[0].text == original.text
        assert result.id_map == {"old-id": stable_chunk_id(chunks[0])}
        assert chunks[0].config_fingerprint == ""
    with pytest.raises(ValueError, match="nonexistent destination"):
        migrate_legacy_store(db, converted)
    with pytest.raises(ValueError, match="separate"):
        migrate_legacy_store(db, db)


def test_failed_legacy_copy_preserves_source_and_removes_partial_destination(
    tmp_path: Path,
) -> None:
    db, converted = tmp_path / "legacy.db", tmp_path / "v2.db"
    create_legacy_database(db, rich_chunk(), malformed=True)
    before = db.read_bytes()
    with pytest.raises(json.JSONDecodeError):
        migrate_legacy_store(db, converted)
    assert db.read_bytes() == before
    assert not converted.exists()


@pytest.mark.parametrize("explicit", [False, True])
def test_opaque_tokenizer_reindexes_unless_fingerprinted(tmp_path: Path, explicit: bool) -> None:
    source = tmp_path / "a.txt"
    source.write_text("text content\n")

    def count(text: str) -> int:
        return len(text)

    if explicit:
        count.fingerprint = "counter-v1"  # type: ignore[attr-defined]
    chunker = Chunker(size_unit="tokens", tokenizer=count)
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(source, chunker=chunker)
        result = store.sync(source, chunker=chunker)
        assert result.files_skipped == int(explicit)
        assert result.files_updated == int(not explicit)


@pytest.mark.parametrize("revision", ["", "parser-v1"])
def test_plugin_revision_controls_persistent_reuse(tmp_path: Path, revision: str) -> None:
    source = tmp_path / "a.py"
    source.write_text("a = 1\n")
    registry = PluginRegistry(revision=revision)
    registry.register_parser("python", lambda _path, _text: None)
    chunker = Chunker(size_unit="chars", registry=registry)
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(source, chunker=chunker)
        result = store.sync(source, chunker=chunker)
        assert result.files_skipped == int(bool(revision))
        registry.revision = "parser-v2"
        assert store.sync(source, chunker=chunker).files_updated == 1


def test_explicit_semantic_provider_namespace_allows_reuse(tmp_path: Path) -> None:
    source = tmp_path / "a.py"
    source.write_text("a = 1\n")
    # Code uses structural routing; provider identity still governs durable reuse.
    chunker = Chunker(
        size_unit="chars",
        semantic_embed_fn=lambda texts: texts,
        semantic_cache_namespace="provider",
        semantic_model_revision="model-v1",
    )
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(source, chunker=chunker)
        assert store.sync(source, chunker=chunker).files_skipped == 1


def test_missing_root_and_ambiguous_options_do_not_change_store(tmp_path: Path) -> None:
    from omnichunk.diff import chunk_diff

    source = tmp_path / "a.txt"
    source.write_text("content\n")
    with ChunkStore(tmp_path / "store.db") as store:
        with pytest.raises(FileNotFoundError):
            store.sync(tmp_path / "missing")
        with pytest.raises(ValueError, match="configured chunker"):
            store.sync(source, chunker=Chunker(), size_unit="chars")
        assert store.query(str(source)) == []
    with pytest.raises(ValueError, match="collection"):
        ChunkStore(tmp_path / "bad.db", collection="")
    with pytest.raises(ValueError, match="configured chunker"):
        chunk_diff("f.py", "f = 1\n", previous_chunks=[], chunker=Chunker(), size_unit="chars")


def test_directory_scan_error_rolls_back_deletion_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omnichunk.store import chunk_store as store_module

    source = tmp_path / "a.txt"
    source.write_text("content\n")
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(tmp_path, glob="**/*.txt", size_unit="chars")
        before = store.query(str(source))
        source.unlink()

        def failed_walk(_path: object, *, onerror: object, followlinks: bool) -> list:
            onerror(PermissionError("unreadable directory"))  # type: ignore[operator]
            return []

        monkeypatch.setattr(store_module.os, "walk", failed_walk)
        with pytest.raises(PermissionError, match="unreadable directory"):
            store.sync(tmp_path, glob="**/*.txt", size_unit="chars")
        assert store.query(str(source)) == before


def test_exported_framework_documents_preserve_identity_and_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class Document:
        def __init__(self, **kwargs: object) -> None:
            self.values = kwargs

    original_import = serialization_module.importlib.import_module

    def imports(name: str) -> object:
        if name == "langchain_core.documents":
            return SimpleNamespace()  # Exercise supported legacy fallback.
        if name in ("langchain.schema", "llama_index.core.schema"):
            return SimpleNamespace(Document=Document)
        return original_import(name)

    monkeypatch.setattr(serialization_module.importlib, "import_module", imports)
    chunk = replace(rich_chunk(), source=SourceDescriptor("doc", "rev"))
    for document in (
        chunks_to_langchain_docs([chunk])[0],
        chunks_to_llamaindex_docs([chunk], use_contextualized_text=False)[0],
    ):
        assert document.values["metadata"]["chunk_id"] == stable_chunk_id(chunk)
        assert document.values["metadata"]["source_id"] == "doc"
        assert document.values["metadata"]["source_revision"] == "rev"
    destination = tmp_path / "chunks.csv"
    payload = chunks_to_csv([chunk], output_path=str(destination))
    assert destination.read_bytes().decode("utf-8") == payload


def test_framework_export_missing_dependencies_have_actionable_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        serialization_module.importlib, "import_module", lambda _name: SimpleNamespace()
    )
    with pytest.raises(ImportError, match="langchain-core"):
        chunks_to_langchain_docs([rich_chunk()])
    with pytest.raises(ImportError, match="llama-index-core"):
        chunks_to_llamaindex_docs([rich_chunk()])


@pytest.mark.parametrize("exporter", [chunks_to_weaviate_objects, chunks_to_supabase_rows])
def test_adapters_reject_missing_vectors(exporter: object) -> None:
    with pytest.raises(ValueError, match="embeddings length"):
        exporter([rich_chunk()], [])  # type: ignore[operator]


def test_converter_rejects_future_store_schema(tmp_path: Path) -> None:
    source = tmp_path / "future.db"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA user_version = 999")
    with pytest.raises(LegacyStoreError, match="Expected legacy"):
        migrate_legacy_store(source, tmp_path / "copy.db")
    assert not (tmp_path / "copy.db").exists()


def test_store_rename_with_retained_source_id_replaces_atomically(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    old, new = root / "old.txt", root / "new.txt"
    old.write_text("unchanged content\n")
    chunker = Chunker(size_unit="chars", source_id="logical-document", context_mode="none")
    with ChunkStore(tmp_path / "store.db") as store:
        store.sync(root, chunker=chunker)
        before = [stable_chunk_id(c) for c in store.query(str(old))]
        old.rename(new)
        result = store.sync(root, chunker=chunker)
        assert result.files_deleted == result.files_updated == 1
        assert store.query(str(old)) == []
        assert [stable_chunk_id(c) for c in store.query(str(new))] == before
