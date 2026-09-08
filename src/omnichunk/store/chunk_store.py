"""Versioned SQLite indexing with scoped deletion and atomic, retryable sync."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from omnichunk.chunker import Chunker, _collect_directory_files
from omnichunk.diff.engine import diff_chunks
from omnichunk.serialization import chunk_from_dict, chunk_to_dict, stable_chunk_id
from omnichunk.types import Chunk, ChunkDiff, SourceDescriptor

STORE_SCHEMA_VERSION = 2


def _norm_path(path: str | Path) -> str:
    return str(Path(path).resolve())


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _cache_reusable(chunker: Chunker) -> bool:
    """Opaque callbacks cannot safely identify behavior across persisted runs."""
    options = chunker._defaults
    for name in ("tokenizer", "semantic_embed_fn", "semantic_sentence_splitter"):
        value = getattr(options, name)
        encoder = (
            name == "tokenizer"
            and not isinstance(value, str)
            and callable(getattr(value, "encode", None))
        )
        if not callable(value) and not encoder:
            continue
        callback = inspect.unwrap(value)
        identity = getattr(callback, "fingerprint", None)
        if isinstance(identity, str) and identity:
            continue
        if (
            name == "semantic_embed_fn"
            and options.semantic_cache_namespace
            and options.semantic_model_revision
        ):
            continue
        return False
    return not chunker.registry.parsers or bool(chunker.registry.revision)


def _diff_chunk_lists(previous: Sequence[Chunk], new: Sequence[Chunk]) -> ChunkDiff:
    """Compatibility alias for the shared content-aware diff implementation."""
    return diff_chunks(previous, new)


@dataclass(frozen=True)
class SyncResult:
    """A committed scan. Exceptions return no success result and roll back the scan.

    Apply ``removed_chunk_ids`` before upserting each diff's ``added`` chunks.
    Same-ID payload changes are included in both for compatibility. Unchanged
    chunks may have moved: refresh their location metadata without re-embedding.
    """

    files_scanned: int
    files_skipped: int
    files_updated: int
    files_deleted: int
    removed_chunk_ids: list[str]
    diffs: dict[str, ChunkDiff]


class LegacyStoreError(ValueError):
    """An old or unknown database must not be mutated by the v2 store."""


@dataclass(frozen=True)
class MigrationResult:
    """Offline copy result; rebuild embeddings for the new occurrence IDs."""

    destination: str
    files_copied: int
    chunks_copied: int
    id_map: dict[str, str]
    reindex_required: bool = True


_SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS files (
    collection TEXT NOT NULL DEFAULT 'default',
    path TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    content_sha256 TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL DEFAULT '',
    last_indexed_at REAL NOT NULL,
    PRIMARY KEY (collection, path)
);
CREATE TABLE IF NOT EXISTS chunks (
    collection TEXT NOT NULL DEFAULT 'default',
    stable_id TEXT NOT NULL,
    filepath TEXT NOT NULL,
    byte_start INTEGER NOT NULL DEFAULT 0,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    chunk_json TEXT NOT NULL,
    PRIMARY KEY (collection, stable_id),
    FOREIGN KEY (collection, filepath) REFERENCES files(collection, path) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS scope_members (
    collection TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    filepath TEXT NOT NULL,
    PRIMARY KEY (collection, scope_key, filepath),
    FOREIGN KEY (collection, filepath) REFERENCES files(collection, path) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chunks_source
    ON chunks(collection, filepath, byte_start, chunk_index);
PRAGMA user_version = 2;
COMMIT;
"""


class ChunkStore:
    """SQLite-backed named collection of chunked documents.

    Directory deletion is limited to a previously completed scan with the same
    resolved root, glob, exclusions and hidden-file policy. A partial file scan
    or a new filter never deletes siblings. Collections are independent.

    One explicit transaction covers a complete sync, including deletions. A
    read/provider/serialization/database failure propagates and preserves the
    last good state so a subsequent sync retries it. The write lock is held
    while processing; use separate connections for concurrent readers.
    """

    def __init__(self, path: str | Path, *, collection: str = "default") -> None:
        if not isinstance(collection, str) or not collection.strip():
            raise ValueError("collection must be a nonempty name")
        self._db_path = Path(path).resolve()
        self.collection = collection
        self._conn = sqlite3.connect(str(self._db_path), isolation_level=None, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        try:
            tables = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if tables and version != STORE_SCHEMA_VERSION:
                raise LegacyStoreError(
                    f"Unsupported store schema {version}; use migrate_legacy_store(old, new) "
                    "with a separate destination or rebuild a new index. "
                    "The old database is unchanged."
                )
            self._conn.execute("PRAGMA foreign_keys = ON")
            if not tables:
                self._conn.executescript(_SCHEMA)
        except BaseException:
            self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ChunkStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def query(self, filepath: str) -> list[Chunk]:
        """Return this collection's chunks in byte/index source order."""
        rows = self._conn.execute(
            "SELECT chunk_json FROM chunks WHERE collection = ? AND filepath = ? "
            "ORDER BY byte_start, chunk_index, stable_id",
            (self.collection, _norm_path(filepath)),
        ).fetchall()
        return [chunk_from_dict(json.loads(row["chunk_json"])) for row in rows]

    def index(
        self,
        root: str | Path,
        *,
        glob: str = "**/*",
        exclude: Sequence[str] | None = None,
        include_hidden: bool = False,
        encoding: str = "utf-8",
        chunker: Chunker | None = None,
        **chunker_options: Any,
    ) -> SyncResult:
        """Re-chunk all matching files, with the same deletion safety as sync."""
        return self._sync(
            root,
            glob=glob,
            exclude=exclude,
            include_hidden=include_hidden,
            encoding=encoding,
            chunker=chunker,
            incremental=False,
            chunker_options=chunker_options,
        )

    def sync(
        self,
        root: str | Path,
        *,
        glob: str = "**/*",
        exclude: Sequence[str] | None = None,
        include_hidden: bool = False,
        encoding: str = "utf-8",
        chunker: Chunker | None = None,
        **chunker_options: Any,
    ) -> SyncResult:
        """Skip only files with unchanged content and processing configuration."""
        return self._sync(
            root,
            glob=glob,
            exclude=exclude,
            include_hidden=include_hidden,
            encoding=encoding,
            chunker=chunker,
            incremental=True,
            chunker_options=chunker_options,
        )

    def _sync(
        self,
        root: str | Path,
        *,
        glob: str,
        exclude: Sequence[str] | None,
        include_hidden: bool,
        encoding: str,
        chunker: Chunker | None,
        incremental: bool,
        chunker_options: dict[str, Any],
    ) -> SyncResult:
        root_path = Path(root).resolve()
        if not root_path.exists():
            raise FileNotFoundError(f"Root does not exist: {root}")
        if chunker is not None and chunker_options:
            raise ValueError("Pass a configured chunker or chunker_options, not both")
        ck = chunker or Chunker(**chunker_options)
        reusable = _cache_reusable(ck)
        fingerprint = _hash_json(
            [
                "omnichunk-store-v2",
                ck.config_fingerprint(),
                encoding,
                type(ck).__module__,
                type(ck).__qualname__,
                ck.registry.revision,
                sorted(ck.registry.parsers),
            ]
        )
        scope_key = _hash_json(
            [
                str(root_path),
                glob,
                sorted(exclude or []),
                include_hidden,
                root_path.is_file(),
            ]
        )
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            paths = self._scan_files(root_path, glob, exclude, include_hidden)
            disk_paths = set(paths)
            previous_scope = {
                row[0]
                for row in self._conn.execute(
                    "SELECT filepath FROM scope_members WHERE collection = ? AND scope_key = ?",
                    (self.collection, scope_key),
                )
            }
            removed: list[str] = []
            diffs: dict[str, ChunkDiff] = {}
            skipped = updated = deleted = 0
            # Only remove missing sources previously owned by this exact completed scan.
            # An existing file excluded by a changed filesystem/filter state is retained.
            for stale in sorted(previous_scope - disk_paths):
                try:
                    Path(stale).stat()
                except FileNotFoundError:
                    removed.extend(
                        row[0]
                        for row in self._conn.execute(
                            "SELECT stable_id FROM chunks WHERE collection = ? AND filepath = ?",
                            (self.collection, stale),
                        )
                    )
                    self._conn.execute(
                        "DELETE FROM files WHERE collection = ? AND path = ?",
                        (self.collection, stale),
                    )
                    deleted += 1
            for filepath in sorted(paths):
                path = Path(filepath)
                stat = path.stat()
                sha = _file_sha256(path)
                row = self._conn.execute(
                    "SELECT content_sha256, config_fingerprint FROM files "
                    "WHERE collection = ? AND path = ?",
                    (self.collection, filepath),
                ).fetchone()
                if (
                    incremental
                    and reusable
                    and row is not None
                    and row["content_sha256"] == sha
                    and row["config_fingerprint"] == fingerprint
                ):
                    skipped += 1
                else:
                    previous = self.query(filepath)
                    chunks = ck.chunk_file(filepath, encoding=encoding)
                    after = path.stat()
                    if (
                        after.st_mtime_ns != stat.st_mtime_ns
                        or after.st_size != stat.st_size
                        or _file_sha256(path) != sha
                    ):
                        raise RuntimeError(f"Source changed while indexing: {filepath}; retry sync")
                    diff = diff_chunks(previous, chunks)
                    diffs[filepath] = diff
                    removed.extend(diff.removed_ids)
                    self._write_document(
                        filepath,
                        stat.st_mtime_ns,
                        stat.st_size,
                        sha,
                        fingerprint,
                        chunks,
                    )
                    updated += 1
                self._conn.execute(
                    "INSERT OR IGNORE INTO scope_members (collection, scope_key, filepath) "
                    "VALUES (?, ?, ?)",
                    (self.collection, scope_key, filepath),
                )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return SyncResult(len(paths), skipped, updated, deleted, sorted(set(removed)), diffs)

    def _scan_files(
        self,
        root: Path,
        glob: str,
        exclude: Sequence[str] | None,
        include_hidden: bool,
    ) -> list[str]:
        if root.is_file():
            candidates = [root]
        else:

            def fail(error: OSError) -> None:
                raise error

            # pathlib glob can suppress directory I/O errors. Verify traversal first
            # so an unreadable subtree cannot masquerade as a completed deletion scan.
            for _ in os.walk(root, onerror=fail, followlinks=False):
                pass
            candidates = _collect_directory_files(
                root,
                glob_pattern=glob,
                exclude_patterns=list(exclude or []),
                include_hidden=include_hidden,
            )
        own_files = {str(self._db_path) + suffix for suffix in ("", "-wal", "-shm", "-journal")}
        paths: set[str] = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            if not root.is_file() and not resolved.is_relative_to(root):
                raise ValueError(f"Source symlink escapes indexing root: {candidate}")
            if str(resolved) not in own_files:
                paths.add(str(resolved))
        return sorted(paths)

    def _write_document(
        self,
        filepath: str,
        mtime_ns: int,
        size: int,
        sha: str,
        fingerprint: str,
        chunks: Sequence[Chunk],
    ) -> None:
        self._conn.execute(
            "INSERT INTO files (collection, path, mtime_ns, size, content_sha256, "
            "config_fingerprint, last_indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(collection, path) DO UPDATE SET mtime_ns=excluded.mtime_ns, "
            "size=excluded.size, content_sha256=excluded.content_sha256, "
            "config_fingerprint=excluded.config_fingerprint, "
            "last_indexed_at=excluded.last_indexed_at",
            (self.collection, filepath, mtime_ns, size, sha, fingerprint, time.time()),
        )
        self._conn.execute(
            "DELETE FROM chunks WHERE collection = ? AND filepath = ?",
            (self.collection, filepath),
        )
        for chunk in chunks:
            self._conn.execute(
                "INSERT INTO chunks (collection, stable_id, filepath, byte_start, chunk_index, "
                "chunk_json) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self.collection,
                    stable_chunk_id(chunk),
                    filepath,
                    chunk.byte_range.start,
                    chunk.index,
                    json.dumps(
                        chunk_to_dict(chunk), ensure_ascii=False, sort_keys=True, allow_nan=False
                    ),
                ),
            )


def migrate_legacy_store(
    source: str | Path,
    destination: str | Path,
    *,
    collection: str = "default",
) -> MigrationResult:
    """Copy a v1 database to a new v2 path without modifying the old database.

    The destination must not exist. Complete metadata present in old JSON is
    retained; already-lost metadata cannot be recreated. Converted records have
    no scan ownership and an empty configuration fingerprint, forcing reindexing
    on the next sync. Missing-source records remain recoverable until an explicit
    new index is built. The returned ID map supports a separate vector rebuild.
    """
    src, dst = Path(source).resolve(), Path(destination).resolve()
    if src == dst or dst.exists():
        raise ValueError("Migration requires a separate, nonexistent destination")
    old = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    created = False
    try:
        version = old.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            raise LegacyStoreError(f"Expected legacy store schema 0 or 1, got {version}")
        old.execute("BEGIN")
        old_files = old.execute("SELECT * FROM files ORDER BY path").fetchall()
        with dst.open("xb"):
            pass
        created = True
        id_map: dict[str, str] = {}
        count = 0
        with ChunkStore(dst, collection=collection) as new:
            new._conn.execute("BEGIN IMMEDIATE")
            try:
                for row in old_files:
                    filepath = _norm_path(row["path"])
                    entries = old.execute(
                        "SELECT stable_id, chunk_json FROM chunks WHERE filepath = ?",
                        (row["path"],),
                    ).fetchall()
                    pairs = [
                        (entry["stable_id"], chunk_from_dict(json.loads(entry["chunk_json"])))
                        for entry in entries
                    ]
                    pairs.sort(key=lambda pair: (pair[1].byte_range.start, pair[1].index, pair[0]))
                    occurrences: dict[str, int] = {}
                    chunks: list[Chunk] = []
                    for old_id, chunk in pairs:
                        occurrence = occurrences.get(chunk.text, 0)
                        occurrences[chunk.text] = occurrence + 1
                        converted = replace(
                            chunk,
                            source=SourceDescriptor(
                                source_id=filepath,
                                revision=row["content_sha256"],
                                normalization="legacy-unknown",
                                format_name="legacy",
                            ),
                            occurrence=occurrence,
                            config_fingerprint="",
                        )
                        chunks.append(converted)
                        id_map[old_id] = stable_chunk_id(converted)
                    new._write_document(
                        filepath,
                        row["mtime_ns"],
                        row["size"],
                        row["content_sha256"],
                        "",
                        chunks,
                    )
                    count += len(chunks)
                new._conn.execute("COMMIT")
            except BaseException:
                new._conn.execute("ROLLBACK")
                raise
        return MigrationResult(str(dst), len(old_files), count, id_map)
    except BaseException:
        if created:
            dst.unlink(missing_ok=True)
        raise
    finally:
        old.close()
