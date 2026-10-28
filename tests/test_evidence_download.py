"""Checks for the optional v3 evidence snapshot restoration."""

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "benchmarks/retrieval/reports/quality-v3/download_evidence.py"
)
spec = importlib.util.spec_from_file_location("download_evidence", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def snapshot(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for name, data, kind in files:
            item = tarfile.TarInfo(module.ARCHIVE_ROOT + name)
            item.type = kind
            item.size = len(data) if kind == tarfile.REGTYPE else 0
            archive.addfile(item, io.BytesIO(data) if item.size else None)
    out.seek(0)
    return out


def test_restore_checks_bytes_and_refuses_overwrite(tmp_path):
    content = b"evidence"
    manifest = {"test/file.json": hashlib.sha256(content).hexdigest()}
    src = snapshot([("test/file.json", content, tarfile.REGTYPE)])
    destination = tmp_path / "evidence"
    module.restore(src, destination, manifest)
    assert (destination / "test/file.json").read_bytes() == content
    with pytest.raises(FileExistsError):
        module.restore(snapshot([]), destination, manifest)


@pytest.mark.parametrize(
    "files,manifest",
    [
        ([("good", b"bad", tarfile.REGTYPE)], {"good": hashlib.sha256(b"correct").hexdigest()}),
        ([], {"missing": hashlib.sha256(b"").hexdigest()}),
        ([("../escape", b"x", tarfile.REGTYPE)], {"good": hashlib.sha256(b"").hexdigest()}),
        ([("good", b"", tarfile.SYMTYPE)], {"good": hashlib.sha256(b"").hexdigest()}),
        (
            [("good", b"", tarfile.REGTYPE), ("good", b"", tarfile.REGTYPE)],
            {"good": hashlib.sha256(b"").hexdigest()},
        ),
    ],
)
def test_rejects_invalid_archive_without_installing(tmp_path, files, manifest):
    destination = tmp_path / "evidence"
    with pytest.raises(ValueError):
        module.restore(snapshot(files), destination, manifest)
    assert not destination.exists()
    assert not (tmp_path / "escape").exists()
