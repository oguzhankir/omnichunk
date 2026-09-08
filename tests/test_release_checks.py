from __future__ import annotations

import importlib.util
import tarfile
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("check_release", SCRIPTS / "check_release.py")
assert spec is not None and spec.loader is not None
check_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_release)


def wheel(
    tmp_path: Path, *, metadata_version: str = "2.1.0", runtime_version: str = "2.1.0"
) -> Path:
    path = tmp_path / "omnichunk-2.1.0-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "omnichunk-2.1.0.dist-info/METADATA", f"Name: omnichunk\nVersion: {metadata_version}\n"
        )
        archive.writestr("omnichunk/_version.py", f'__version__ = "{runtime_version}"\n')
        archive.writestr("omnichunk/py.typed", "")
    return path


def test_wheel_requires_metadata_runtime_source_and_tag_agreement(tmp_path: Path) -> None:
    path = wheel(tmp_path)
    assert check_release.inspect_wheel(path, expected_version="2.1.0", tag="v2.1.0") == "2.1.0"


@pytest.mark.parametrize(
    "metadata_version,runtime_version,expected,tag",
    [
        ("2.1.0", "0.10.1", "2.1.0", "v2.1.0"),
        ("2.1.0", "2.1.0", "2.0.0", "v2.1.0"),
        ("2.1.0", "2.1.0", "2.1.0", "v2.0.0"),
    ],
)
def test_mismatched_release_versions_are_rejected(
    tmp_path: Path, metadata_version: str, runtime_version: str, expected: str, tag: str
) -> None:
    path = wheel(tmp_path, metadata_version=metadata_version, runtime_version=runtime_version)
    with pytest.raises(ValueError, match="version"):
        check_release.inspect_wheel(path, expected_version=expected, tag=tag)


def test_source_version_is_parsed_without_executing_file(tmp_path: Path) -> None:
    source = tmp_path / "_version.py"
    source.write_text('raise RuntimeError("must not execute")\n__version__ = "1.2.3"\n')
    assert check_release.read_source_version(source) == "1.2.3"
    source.write_text("__version__ = compute_version()\n")
    with pytest.raises(ValueError, match="literal"):
        check_release.read_source_version(source)


def test_sdist_metadata_must_match_wheel(tmp_path: Path) -> None:
    path = tmp_path / "omnichunk-2.1.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        payload = b"Name: omnichunk\nVersion: 2.0.0\n"
        info = tarfile.TarInfo("omnichunk-2.1.0/PKG-INFO")
        info.size = len(payload)
        archive.addfile(info, BytesIO(payload))
    with pytest.raises(ValueError, match="version"):
        check_release.inspect_sdist(path, expected_version="2.1.0")


def test_same_version_stale_wheel_source_is_rejected(tmp_path: Path) -> None:
    path = wheel(tmp_path)
    source = tmp_path / "src"
    source.mkdir()
    (source / "_version.py").write_text('__version__ = "2.1.0"\n')
    (source / "new_feature.py").write_text("FEATURE = True\n")
    with pytest.raises(ValueError, match="source differs"):
        check_release.inspect_wheel(path, expected_version="2.1.0", source_root=source)


def test_release_tag_must_identify_built_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    revisions = iter(["new-commit\n", "old-commit\n"])
    monkeypatch.setattr(
        check_release.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=next(revisions)),
    )
    with pytest.raises(ValueError, match="current checkout"):
        check_release.verify_release_checkout("v2.1.0")
