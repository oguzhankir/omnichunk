#!/usr/bin/env python3
"""Verify and restore original evidence source bytes using only Python's stdlib."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import zlib
from pathlib import Path, PurePosixPath
from typing import Any


class EvidenceError(ValueError):
    """The archive, path mapping or existing destination is invalid."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_parts(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise EvidenceError(f"Invalid {label}")
    parts = value.split("/")
    if PurePosixPath(value).is_absolute() or any(
        part in {"", ".", ".."} or ":" in part for part in parts
    ):
        raise EvidenceError(f"Unsafe {label}: {value!r}")
    return tuple(parts)


def source_destination(source: Any, published: tuple[str, ...]) -> tuple[str, ...]:
    if (
        not isinstance(source, str)
        or not source.startswith("/")
        or "\\" in source
        or "\0" in source
    ):
        raise EvidenceError("Source path must be an absolute POSIX path")
    if any(part in {"", ".", ".."} for part in source.split("/")[1:]):
        raise EvidenceError("Unsafe original source path")
    prefix = "/workspace/work/"
    if source.startswith(prefix):
        return relative_parts(source[len(prefix) :], "rebased source path")
    return ("other-sources", *published)


def contained(root: Path, parts: tuple[str, ...]) -> Path:
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise EvidenceError(f"Symlink component is forbidden: {current}")
    if not current.resolve(strict=False).is_relative_to(root):
        raise EvidenceError(f"Path escapes selected directory: {current}")
    return current


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise EvidenceError(f"Non-finite JSON number: {value}")


def checked_payload(archive: Path, row: dict[str, Any]) -> bytes:
    published = relative_parts(row.get("published_relative_path"), "published path")
    path = contained(archive, published)
    if not path.is_file():
        raise EvidenceError(f"Missing archive artifact: {path}")
    for name in ("stored_sha256", "raw_sha256", "source_sha256"):
        if not isinstance(row.get(name), str) or not re.fullmatch(r"[0-9a-f]{64}", row[name]):
            raise EvidenceError(f"Invalid {name}: {path}")
    for name in ("stored_size_bytes", "raw_size_bytes", "source_size_bytes"):
        if type(row.get(name)) is not int or row[name] < 0:
            raise EvidenceError(f"Invalid {name}: {path}")
    if type(row.get("source_was_gzip")) is not bool or row.get("encoding") not in {
        "gzip",
        "identity",
    }:
        raise EvidenceError(f"Invalid encoding policy: {path}")
    if row["source_was_gzip"] and row["encoding"] != "gzip":
        raise EvidenceError(f"Inconsistent original gzip policy: {path}")
    stored = path.read_bytes()
    if len(stored) != row["stored_size_bytes"] or digest(stored) != row["stored_sha256"]:
        raise EvidenceError(f"Stored hash/size mismatch: {path}")
    try:
        raw = gzip.decompress(stored) if row["encoding"] == "gzip" else stored
    except (OSError, EOFError, zlib.error) as exc:
        raise EvidenceError(f"Invalid gzip artifact: {path}") from exc
    if len(raw) != row["raw_size_bytes"] or digest(raw) != row["raw_sha256"]:
        raise EvidenceError(f"Raw hash/size mismatch: {path}")
    original = stored if row["source_was_gzip"] else raw
    if len(original) != row["source_size_bytes"] or digest(original) != row["source_sha256"]:
        raise EvidenceError(f"Original source hash/size mismatch: {path}")
    return original


def restore(archive_root: Path, output_dir: Path) -> dict[str, Any]:
    archive = archive_root.resolve(strict=True)
    output = output_dir.resolve(strict=False)
    if not archive.is_dir():
        raise EvidenceError("--archive-root must be a directory")
    if archive.is_relative_to(output) or output.is_relative_to(archive):
        raise EvidenceError("Archive and output directories must not overlap")
    map_path = contained(archive, ("storage-map-v2.json",))
    data = json.loads(
        map_path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_pairs,
        parse_constant=reject_constant,
    )
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 2:
        raise EvidenceError("Expected storage-map-v2.json with version 2")
    rows = data.get("entries")
    if not isinstance(rows, list) or not rows:
        raise EvidenceError("Storage map must contain nonempty entries")
    planned: list[tuple[dict[str, Any], tuple[str, ...]]] = []
    destinations: set[tuple[str, ...]] = set()
    # Verify every input and conflict before creating output files.
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError("Storage entries must be objects")
        published = relative_parts(row.get("published_relative_path"), "published path")
        parts = source_destination(row.get("source_absolute_path"), published)
        if parts in destinations:
            raise EvidenceError(f"Duplicate restore destination: {'/'.join(parts)}")
        destinations.add(parts)
        original = checked_payload(archive, row)
        target = contained(output, parts)
        if target.exists() and (
            not target.is_file()
            or target.stat().st_size != len(original)
            or digest(target.read_bytes()) != row["source_sha256"]
        ):
            raise EvidenceError(f"Refusing to overwrite differing destination: {target}")
        planned.append((row, parts))
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    written = skipped = restored_bytes = 0
    for row, parts in planned:
        original = checked_payload(archive, row)  # Revalidate against changes between passes.
        target = contained(output, parts)
        if target.exists():
            if (
                not target.is_file()
                or target.stat().st_size != len(original)
                or digest(target.read_bytes()) != row["source_sha256"]
            ):
                raise EvidenceError(f"Refusing to overwrite differing destination: {target}")
            skipped += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target = contained(output, parts)
            try:
                with target.open("xb") as handle:
                    handle.write(original)
            except FileExistsError as exc:
                raise EvidenceError(f"Destination appeared during restoration: {target}") from exc
            written += 1
        if (
            target.stat().st_size != row["source_size_bytes"]
            or digest(target.read_bytes()) != row["source_sha256"]
        ):
            raise EvidenceError(f"Restored bytes do not match: {target}")
        restored_bytes += len(original)
    return {
        "status": "passed",
        "entries": len(planned),
        "written": written,
        "identical_skipped": skipped,
        "restored_source_bytes": restored_bytes,
        "archive_root": str(archive),
        "output_dir": str(output),
        "storage_map_sha256": digest(map_path.read_bytes()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = restore(args.archive_root, args.output_dir)
    except (EvidenceError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"Evidence restoration failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
