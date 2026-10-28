#!/usr/bin/env python3
"""Restore the v3 evidence from the immutable GitHub source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

COMMIT = "f273ed6474da1beaf7b73f53d802d7f9b7c46699"
URL = f"https://github.com/oguzhankir/omnichunk/archive/{COMMIT}.tar.gz"
ARCHIVE_ROOT = f"omnichunk-{COMMIT}/benchmarks/retrieval/reports/quality-v3/evidence/"
HERE = Path(__file__).resolve().parent


def restore(stream, destination: Path, manifest: dict[str, str]) -> None:
    """Verify each expected regular file before atomically installing the directory."""
    if os.path.lexists(destination):
        raise FileExistsError(f"Destination already exists: {destination}")
    for name, digest in manifest.items():
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or str(path) != name
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError(f"Invalid manifest entry: {name!r}")
    if not manifest:
        raise ValueError("Empty manifest")
    seen: set[str] = set()
    with tempfile.TemporaryDirectory(prefix=".evidence-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "evidence"
        stage.mkdir()
        with tarfile.open(fileobj=stream, mode="r|gz") as archive:
            for member in archive:
                if not member.name.startswith(ARCHIVE_ROOT):
                    continue
                name = member.name[len(ARCHIVE_ROOT) :]
                if member.isdir():
                    continue
                if name not in manifest or not member.isfile() or name in seen:
                    raise ValueError(f"Invalid or duplicate archive member: {member.name}")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"Cannot read archive member: {member.name}")
                target = stage.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with source, target.open("xb") as output:
                    while block := source.read(1024 * 1024):
                        digest.update(block)
                        output.write(block)
                if digest.hexdigest() != manifest[name]:
                    raise ValueError(f"SHA-256 mismatch: {name}")
                seen.add(name)
        missing = set(manifest) - seen
        if missing:
            raise ValueError(f"Archive is missing {len(missing)} expected files")
        if os.path.lexists(destination):
            raise FileExistsError(f"Destination appeared during restore: {destination}")
        stage.rename(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a local snapshot tar.gz")
    args = parser.parse_args()
    manifest = json.loads((HERE / "evidence-sha256.json").read_text(encoding="utf-8"))
    with args.archive.open("rb") if args.archive else urlopen(URL, timeout=60) as stream:
        restore(stream, HERE / "evidence", manifest)
    print(f"Restored and verified {len(manifest)} evidence files in {HERE / 'evidence'}")


if __name__ == "__main__":
    main()
