"""Validate built distribution versions and smoke-test an isolated installed wheel."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tarfile
import tempfile
import venv
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def _literal_version(source: str) -> str:
    for statement in ast.parse(source).body:
        if (
            isinstance(statement, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in statement.targets
            )
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            return statement.value.value
    raise ValueError("Runtime version must be a literal __version__ assignment")


def read_source_version(path: Path) -> str:
    return _literal_version(path.read_text(encoding="utf-8"))


def _metadata_version(text: str, *, expected_version: str) -> str:
    metadata = Parser().parsestr(text)
    if metadata.get("Name") != "omnichunk":
        raise ValueError("Distribution name must be omnichunk")
    version = metadata.get("Version", "")
    if version != expected_version:
        raise ValueError(
            f"Distribution version {version!r} != expected version {expected_version!r}"
        )
    return version


def inspect_wheel(
    wheel: Path,
    *,
    expected_version: str,
    tag: str | None = None,
    source_root: Path | None = None,
) -> str:
    """Require wheel metadata, packaged runtime source, expected source and tag agreement."""
    with ZipFile(wheel) as archive:
        metadata_files = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            raise ValueError("Wheel must contain exactly one METADATA file")
        version = _metadata_version(
            archive.read(metadata_files[0]).decode("utf-8"), expected_version=expected_version
        )
        runtime = _literal_version(archive.read("omnichunk/_version.py").decode("utf-8"))
        if runtime != version:
            raise ValueError(
                f"Packaged runtime version {runtime!r} != metadata version {version!r}"
            )
        if "omnichunk/py.typed" not in archive.namelist():
            raise ValueError("Wheel must ship the PEP 561 py.typed marker")
        if source_root is not None:
            expected_files = {
                "omnichunk/" + path.relative_to(source_root).as_posix(): path.read_bytes()
                for path in source_root.rglob("*.py")
            }
            packaged_files = {
                name: archive.read(name)
                for name in archive.namelist()
                if name.startswith("omnichunk/") and name.endswith(".py")
            }
            if packaged_files != expected_files:
                raise ValueError("Wheel Python source differs from the validated checkout")
    if tag is not None and tag.removeprefix("v") != version:
        raise ValueError(f"Release tag {tag!r} != wheel version {version!r}")
    return version


def verify_release_checkout(tag: str) -> None:
    """A published tag must point at the clean checkout used for the build."""
    revisions = []
    for reference in ("HEAD", f"{tag}^{{commit}}"):
        revisions.append(
            subprocess.run(
                ["git", "rev-parse", "--verify", "--end-of-options", reference],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    if revisions[0] != revisions[1]:
        raise ValueError("Release tag does not identify the current checkout")
    subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", "src", "pyproject.toml"], cwd=ROOT, check=True
    )


def inspect_sdist(sdist: Path, *, expected_version: str) -> None:
    with tarfile.open(sdist, "r:gz") as archive:
        candidates = [
            member
            for member in archive.getmembers()
            if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")
        ]
        if len(candidates) != 1 or not candidates[0].isfile():
            raise ValueError("Source distribution must contain one root PKG-INFO")
        stream = archive.extractfile(candidates[0])
        if stream is None:
            raise ValueError("Source distribution metadata cannot be read")
        _metadata_version(stream.read().decode("utf-8"), expected_version=expected_version)


def smoke_installed_wheel(wheel: Path, *, expected_version: str) -> None:
    """Install only the wheel into a clean environment; no optional dependencies or network."""
    with tempfile.TemporaryDirectory(prefix="omnichunk-release-") as temporary:
        environment = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--disable-pip-version-check",
                str(wheel.resolve()),
            ],
            check=True,
            cwd=environment,
        )
        code = """
import importlib.metadata
import json
import sys
import omnichunk
expected = sys.argv[1]
assert importlib.metadata.version('omnichunk') == omnichunk.__version__ == expected
source = 'café 🙂 source text\\n' * 4
chunker = omnichunk.Chunker(size_unit='chars', max_chunk_size=32, min_chunk_size=1)
chunks = chunker.chunk('x.txt', source)
assert chunks and ''.join(chunk.text for chunk in chunks) == source
raw = source.encode('utf-8')
for chunk in chunks:
    assert raw[chunk.byte_range.start:chunk.byte_range.end].decode('utf-8') == chunk.text
assert all(module not in sys.modules for module in ('numpy', 'tree_sitter', 'tiktoken'))
print(json.dumps({'version': omnichunk.__version__, 'chunks': len(chunks),
                  'minimal_install': True}))
"""
        subprocess.run(
            [str(python), "-I", "-c", code, expected_version], check=True, cwd=environment
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--tag", help="Required by publishing workflow; must match built version")
    parser.add_argument("--version-file", type=Path, default=ROOT / "src/omnichunk/_version.py")
    args = parser.parse_args(argv)
    wheels, sdists = sorted(args.dist_dir.glob("*.whl")), sorted(args.dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        parser.error("dist-dir must contain exactly one wheel and one source distribution")
    expected = read_source_version(args.version_file)
    if args.tag is not None:
        verify_release_checkout(args.tag)
    inspect_wheel(
        wheels[0], expected_version=expected, tag=args.tag, source_root=ROOT / "src/omnichunk"
    )
    inspect_sdist(sdists[0], expected_version=expected)
    subprocess.run(
        [sys.executable, "-m", "twine", "check", "--strict", str(wheels[0]), str(sdists[0])],
        check=True,
    )
    smoke_installed_wheel(wheels[0], expected_version=expected)
    print(json.dumps({"version": expected, "tag": args.tag, "artifact_checks": "passed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
