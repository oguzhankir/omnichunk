"""
Persistent SQLite-backed chunk cache with incremental sync (mtime + content hash).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omnichunk.chunker import Chunker, _collect_directory_files
from omnichunk.serialization import chunk_from_dict, chunk_to_dict, stable_chunk_id
from omnichunk.types import Chunk, ChunkDiff


def _norm_path(path: str | Path) -> str:
    return str(Path(path).resolve())


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _diff_chunk_lists(previous: Sequence[Chunk], new: Sequence[Chunk]) -> ChunkDiff:
    prev_ids: set[str] = {stable_chunk_id(c) for c in previous}
    new_ids: set[str] = set()
    added: list[Chunk] = []
    unchanged: list[Chunk] = []
    for c in new:
        cid = stable_chunk_id(c)
        new_ids.add(cid)
        if cid in prev_ids:
            unchanged.append(c)
        else:
            added.append(c)
    removed_ids = sorted(prev_ids - new_ids)
    return ChunkDiff(added=added, removed_ids=removed_ids, unchanged=unchanged)


@dataclass(frozen=True)
class SyncResult:
    """Summary of a sync or index run."""

    files_scanned: int
    files_skipped: int
    files_updated: int
    files_deleted: int
    removed_chunk_ids: list[str]
    """Stable IDs removed (deleted files + chunks dropped on re-chunk)."""
    diffs: dict[str, ChunkDiff]
    """Per-file diff for paths that were re-chunked (non-empty previous chunks)."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    mtime_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    content_sha256 TEXT NOT NULL,
    last_indexed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    stable_id TEXT PRIMARY KEY,
    filepath TEXT NOT NULL,
    chunk_json TEXT NOT NULL,
    FOREIGN KEY (filepath) REFERENCES files(path) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_filepath ON chunks(filepath);
"""


class ChunkStore:
    """SQLite-backed store for chunked documents; supports incremental sync."""

    def __init__(self, path: str | Path) -> None:
        self._db_path = Path(path)
        self._conn = sqlite3.connect(str(self._db_path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ChunkStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def query(self, filepath: str) -> list[Chunk]:
        """Return cached chunks for a file path (resolved), newest index order."""
        fp = _norm_path(filepath)
        cur = self._conn.execute(
            "SELECT chunk_json FROM chunks WHERE filepath = ? ORDER BY stable_id",
            (fp,),
        )
        rows = cur.fetchall()
        return [chunk_from_dict(json.loads(r["chunk_json"])) for r in rows]

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
        """Full scan: index all matching files (re-chunks even if cache matches)."""
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
        """Incremental sync: skip files whose mtime, size, and content hash are unchanged."""
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

        ck = chunker or Chunker(**chunker_options)

        if root_path.is_file():
            file_paths = [root_path]
        else:
            file_paths = _collect_directory_files(
                root_path,
                glob_pattern=glob,
                exclude_patterns=list(exclude or []),
                include_hidden=include_hidden,
            )

        disk_norm = {_norm_path(p): p for p in file_paths}
        removed_chunk_ids: list[str] = []
        diffs: dict[str, ChunkDiff] = {}
        files_scanned = len(disk_norm)
        files_skipped = 0
        files_updated = 0

        cur = self._conn.execute("SELECT path FROM files")
        db_paths = {r["path"] for r in cur.fetchall()}
        disk_paths = set(disk_norm.keys())

        for stale in sorted(db_paths - disk_paths):
            cur = self._conn.execute(
                "SELECT stable_id FROM chunks WHERE filepath = ?",
                (stale,),
            )
            removed_chunk_ids.extend(r["stable_id"] for r in cur.fetchall())
            self._conn.execute("DELETE FROM files WHERE path = ?", (stale,))

        files_deleted = len(db_paths - disk_paths)

        now = time.time()
        for fp_str in sorted(disk_norm.keys()):
            path = disk_norm[fp_str]
            try:
                st = path.stat()
            except OSError:
                continue
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
            size = st.st_size
            try:
                sha = _file_sha256(path)
            except OSError:
                continue

            if incremental:
                row = self._conn.execute(
                    "SELECT mtime_ns, size, content_sha256 FROM files WHERE path = ?",
                    (fp_str,),
                ).fetchone()
                if row is not None and (
                    row["mtime_ns"] == mtime_ns
                    and row["size"] == size
                    and row["content_sha256"] == sha
                ):
                    files_skipped += 1
                    continue

            prev_chunks = self.query(fp_str)
            try:
                new_chunks = ck.chunk_file(str(path), encoding=encoding)
            except Exception:
                new_chunks = []

            diff = _diff_chunk_lists(prev_chunks, new_chunks)
            if prev_chunks:
                diffs[fp_str] = diff
            removed_chunk_ids.extend(diff.removed_ids)

            with self._conn:
                self._conn.execute("DELETE FROM chunks WHERE filepath = ?", (fp_str,))
                self._conn.execute("DELETE FROM files WHERE path = ?", (fp_str,))
                self._conn.execute(
                    """
                    INSERT INTO files (path, mtime_ns, size, content_sha256, last_indexed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (fp_str, mtime_ns, size, sha, now),
                )
                for ch in new_chunks:
                    sid = stable_chunk_id(ch)
                    payload = json.dumps(chunk_to_dict(ch), ensure_ascii=False, sort_keys=True)
                    self._conn.execute(
                        """
                        INSERT INTO chunks (stable_id, filepath, chunk_json)
                        VALUES (?, ?, ?)
                        """,
                        (sid, fp_str, payload),
                    )

            files_updated += 1

        return SyncResult(
            files_scanned=files_scanned,
            files_skipped=files_skipped,
            files_updated=files_updated,
            files_deleted=files_deleted,
            removed_chunk_ids=removed_chunk_ids,
            diffs=diffs,
        )
